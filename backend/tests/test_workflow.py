from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agent import build_graph
from app.demo_model import DemoModel
from app.memory.extract import ScriptedPolicy
from app.memory.store import MemoryStore
from app.papers import PaperCorpus


async def test_root_streaming_and_fresh_thread_after_restart(settings):
    graph = build_graph(settings, checkpointer=InMemorySaver())
    first_config = {"configurable": {"thread_id": "first"}}
    updates = []
    custom = []
    chunks = []
    async for mode, data in graph.astream(
        {"messages": [HumanMessage(content="I have one week for memory research.", id="u1")]},
        config=first_config,
        stream_mode=["updates", "messages", "custom"],
    ):
        if mode == "updates":
            updates.extend(value for value in data.values() if value)
        elif mode == "custom":
            custom.append(data)
        else:
            chunks.append(data)
    assert chunks, "Model messages must stream through the middleware"
    assert any(u.get("todos", [{}])[0].get("status") == "in_progress" for u in updates)
    assert any(u.get("files") for u in updates)
    assert custom == [{"memory_status": "updating"}, {"memory_status": "ready"}]
    first = (await graph.aget_state(first_config)).values
    assert len(first["files"]) == 1
    assert all(task["status"] == "completed" for task in first["todos"])
    assert first["memory_changes"]
    tool_names = [m.name for m in first["messages"] if isinstance(m, ToolMessage)]
    assert tool_names.count("read_paper") == 2
    assert "task" not in tool_names
    # Brand-new graph/checkpointer, same SQLite store: no old thread state survives.
    restarted = build_graph(settings, checkpointer=InMemorySaver())
    second = await restarted.ainvoke(
        {"messages": [HumanMessage(content="Design a memory research experiment.", id="u2")]},
        config={"configurable": {"thread_id": "second"}},
    )
    assert second["recalled_memories"][0]["text"] == "I have one week for memory research."
    assert len([m for m in second["messages"] if isinstance(m, HumanMessage)]) == 1
    assert set(first["files"]).isdisjoint(second["files"])
    report = next(iter(second["files"].values()))["content"]
    assert "one week" in report
    assert "memory:" in report and "source:" in report and "paper:amem:S2" in report
    assert not any(m.id == "u1" for m in second["messages"])


class FailingModel(DemoModel):
    def _generate(self, *args, **kwargs):
        raise RuntimeError("Simulated model failure")


async def test_failed_run_does_not_save_memory(settings):
    import pytest

    graph = build_graph(settings, model=FailingModel())
    with pytest.raises(RuntimeError, match="Simulated model failure"):
        await graph.ainvoke(
            {"messages": [HumanMessage(content="unsaved memory", id="u")]},
            config={"configurable": {"thread_id": "failed"}},
        )
    assert MemoryStore(settings.db_path).search(settings.project_id, "unsaved memory") == []


def test_paper_ids_and_unknown_path(settings):
    corpus = PaperCorpus(settings.papers_dir)
    assert len(corpus.papers) == 3
    hit = corpus.search("amem")[0]
    paper = corpus.read(hit["paper_id"])
    assert hit["source_id"] == paper["sections"][0]["source_id"]
    assert corpus.read("../../.env")["error"] == "Unknown paper ID"


async def test_changed_constraint_is_current_in_fresh_graph(settings):
    graph = build_graph(settings)
    await graph.ainvoke(
        {"messages": [HumanMessage(content="I have four weeks for research.", id="first")]},
        config={"configurable": {"thread_id": "first"}},
    )
    await graph.ainvoke(
        {"messages": [HumanMessage(content="I now have one week for research.", id="second")]},
        config={"configurable": {"thread_id": "second"}},
    )
    fresh = await build_graph(settings).ainvoke(
        {"messages": [HumanMessage(content="Design my research experiment.", id="fresh")]},
        config={"configurable": {"thread_id": "fresh"}},
    )
    constraints = [n for n in fresh["recalled_memories"] if n["kind"] == "constraint"]
    assert len(constraints) == 1
    assert constraints[0]["text"] == "I now have one week for research."
    report = next(iter(fresh["files"].values()))["content"]
    assert "one week" in report and "four weeks" not in report
    note = MemoryStore(settings.db_path).inspect(
        settings.project_id,
        constraints[0]["id"],
    )
    assert len(note["versions"]) == 2


async def test_consolidation_failure_keeps_answer_and_files(settings):
    class BrokenPolicy(ScriptedPolicy):
        def extract(self, context):
            raise ValueError("Invalid structured output")

    graph = build_graph(settings, memory_policy=BrokenPolicy())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="I have one week.", id="failed-ingestion")]},
        config={"configurable": {"thread_id": "failed-ingestion"}},
    )
    assert result["messages"][-1].text
    assert result["files"]
    assert result["memory_status"] == "error"
    assert result["memory_changes"] == []
    store = MemoryStore(settings.db_path)
    assert store.search(settings.project_id, "one week") == []
    with store.connection() as db:
        locations = db.execute(
            "SELECT source_location FROM source_events WHERE tool_name='read_paper'",
        ).fetchall()
        assert len(locations) == 2
        assert all('"source_id": "paper:' in row[0] for row in locations)
