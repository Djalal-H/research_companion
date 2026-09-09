import json
from pathlib import Path

import httpx

from app.demo import run_demo
from app.http import create_app
from app.memory.extract import ScriptedPolicy
from app.memory.inspection import inspect_interaction, inspect_note
from app.memory.reconcile import MemoryEngine
from app.memory.store import MemoryStore, stable_id


def exchange(text, prefix="u"):
    return [
        {"id": prefix, "role": "human", "content": text},
        {"id": prefix + "a", "role": "ai", "content": "Acknowledged."},
    ]


async def test_routes_scope_allowlist_and_idempotent_operations(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ScriptedPolicy())
    events = exchange("I have one week.")
    ids = engine.ingest(settings.project_id, "thread", events)
    interaction_id = stable_id(settings.project_id, "thread", "u")
    before = inspect_interaction(store, settings.project_id, interaction_id).model_dump()
    assert engine.ingest(settings.project_id, "thread", events) == ids
    assert inspect_interaction(store, settings.project_id, interaction_id).model_dump() == before
    engine.ingest(settings.project_id, "thread2", events)
    repeat = inspect_interaction(
        store, settings.project_id, stable_id(settings.project_id, "thread2", "u")
    )
    assert [op.action for op in repeat.operations] == ["NOOP"]
    assert repeat.note_ids == []
    other = engine.ingest("other", "thread", events)[0]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        for path in [f"notes/{ids[0]}", f"interactions/{interaction_id}"]:
            response = await client.get(f"/memory/{path}")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            payload = response.json()
            assert payload["evidence"][0]["content"] == "I have one week."
            assert payload["operations"][0]["reason"]
            assert "embedding" not in json.dumps(payload)
            assert "prompt_version" not in json.dumps(payload)
            assert "model_version" not in json.dumps(payload)
        for path in [
            "notes/missing",
            "interactions/missing",
            f"notes/{other}",
            f"interactions/{stable_id('other', 'thread', 'u')}",
        ]:
            assert (await client.get(f"/memory/{path}")).status_code == 404
        assert (await client.post(f"/memory/notes/{ids[0]}")).status_code == 405


async def test_three_session_demo_and_evolved_inspection(settings):
    configured = settings.model_copy(
        update={
            "papers_dir": Path(__file__).resolve().parents[2] / "data/papers",
            "memory_budget": 10000,
        }
    )
    sessions = await run_demo(configured)
    store = MemoryStore(settings.db_path)
    second = sessions[1]
    committed = inspect_interaction(store, settings.project_id, second["memory_interaction_id"])
    assert second["memory_operations"] == [op.model_dump() for op in committed.operations]
    evolved_id = next(op.target_note_ids[0] for op in committed.operations if op.action == "EVOLVE")
    note = inspect_note(store, settings.project_id, evolved_id)
    assert note.origin == "paper"
    assert len(note.versions) == 1
    assert len(note.versions[0].metadata_history) == 2
    assert "changing facts" in note.versions[0].metadata.context
    assert note.connections
    assert all(link.neighbor_text and link.neighbor_version_id for link in note.connections)
    assert all(source.role == "tool" for source in note.versions[0].sources)


def test_scripted_paper_extraction_requires_observed_tool_evidence():
    context = {"current": [{"id": "u", "role": "human", "content": "Compare A-MEM."}], "recent": []}
    assert ScriptedPolicy().extract(context).candidates == []
    context["current"].append({"id": "a", "role": "ai", "content": "A-MEM uses notes."})
    assert ScriptedPolicy().extract(context).candidates == []


def test_pending_failure_inspection(settings):
    class Broken(ScriptedPolicy):
        def extract(self, context):
            raise ValueError("private prompt must not be exposed")

    import pytest

    store = MemoryStore(settings.db_path)
    events = exchange("I have one week.")
    with pytest.raises(ValueError):
        MemoryEngine(store, Broken()).ingest(settings.project_id, "failed", events)
    identifier = stable_id(settings.project_id, "failed", "u")
    detail = inspect_interaction(store, settings.project_id, identifier)
    assert detail.status == "pending"
    assert detail.note_ids == []
    assert detail.operations[0].status == "failed"
    assert "private prompt" not in detail.model_dump_json()
    MemoryEngine(store, ScriptedPolicy()).retry(settings.project_id, "failed", identifier)
    recovered = inspect_interaction(store, settings.project_id, identifier)
    assert recovered.status == "completed"
    assert {op.status for op in recovered.operations} == {"failed", "completed"}
