"""Repeatable Day 5 smoke scenario. Always uses a disposable isolated database."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agent import build_graph
from app.config import Settings
from app.memory.inspection import inspect_interaction, inspect_note
from app.memory.store import MemoryStore

PROMPTS = [
    "Compare A-MEM and Mem0. I’m interested in retrieval quality.",
    "I only have a week. Let’s focus on handling changing facts.",
    "Design the smallest experiment for my project, and explain our choices.",
]


async def run_demo(settings):
    graph = build_graph(settings, checkpointer=InMemorySaver())
    sessions = []
    for index, prompt in enumerate(PROMPTS):
        if index == 2:
            graph = build_graph(settings, checkpointer=InMemorySaver())
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content=prompt, id=f"demo-user-{index}")]},
            config={"configurable": {"thread_id": f"demo-session-{index}"}},
        )
        assert state["memory_status"] == "ready", "Consolidation failed"
        assert all(todo["status"] == "completed" for todo in state["todos"])
        sessions.append(state)
    store = MemoryStore(settings.db_path)
    final = sessions[-1]
    assert len([m for m in final["messages"] if isinstance(m, HumanMessage)]) == 1
    assert not set(final["files"]).intersection(sessions[0]["files"] | sessions[1]["files"])
    recalled = final["recalled_memories"]
    assert any("changing facts" in note["text"] for note in recalled)
    assert any("a week" in note["text"] for note in recalled)
    assert not any("retrieval quality" in note["text"] for note in recalled)
    assert any(note["origin"] == "paper" for note in recalled)
    change = inspect_interaction(store, settings.project_id, sessions[1]["memory_interaction_id"])
    assert {"SUPERSEDE", "EVOLVE", "LINK"} <= {op.action for op in change.operations}
    objective = next(note for note in recalled if note["kind"] == "preference")
    detail = inspect_note(store, settings.project_id, objective["id"])
    assert len(detail.versions) == 2
    assert any("retrieval quality" in v.text and v.status == "superseded" for v in detail.versions)
    assert any(link.status == "active" for link in detail.connections)
    assert any(link.status == "historical" for link in detail.connections)
    report = next(iter(final["files"].values()))["content"]
    if isinstance(report, list):
        report = "\n".join(report)
    assert "changing facts" in report and "week" in report
    assert "memory:" in report and "source:" in report and "paper:" in report
    assert "not an accepted user decision" in report
    return sessions


async def main():
    with TemporaryDirectory(prefix="research-day5-") as directory:
        settings = Settings(
            model="demo", db_path=Path(directory) / "memory.sqlite3", memory_budget=10000
        )
        sessions = await run_demo(settings)
        for index, session in enumerate(sessions, 1):
            print(
                f"Session {index}: {len(session['recalled_memories'])} recalled, "
                f"{len(session['memory_operations'])} committed operations"
            )
        print("PASS: fresh-thread report, changed objective, evidence, evolution, and connections.")
        print("Scripted lexical demo only; browser and live-provider quality are not verified.")


if __name__ == "__main__":
    asyncio.run(main())
