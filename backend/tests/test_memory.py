import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.memory.extract import ScriptedPolicy
from app.memory.reconcile import MemoryEngine
from app.memory.store import MemoryStore


def ingest(store, *args):
    return MemoryEngine(store, ScriptedPolicy()).ingest(*args)


def exchange(text="I have one week for memory research.", message_id="u1"):
    return [
        {"id": message_id, "role": "human", "content": text},
        {"id": "a-" + message_id, "role": "ai", "content": "Try a year-long experiment."},
    ]


def test_restart_scope_and_provenance(settings):
    store = MemoryStore(settings.db_path)
    ids = ingest(store, "project-a", "thread-a", exchange())
    reopened = MemoryStore(settings.db_path)
    result = reopened.search("project-a", "one week memory")
    assert [note["id"] for note in result] == ids
    note = reopened.inspect("project-a", ids[0])
    assert note["sources"][0]["thread_id"] == "thread-a"
    assert note["sources"][0]["role"] == "human"
    assert note["sources"][0]["content"] == exchange()[0]["content"]
    assert reopened.inspect("project-b", ids[0]) is None
    assert reopened.search("project-b", "one week memory") == []
    assert reopened.search("project-a", "year-long") == []
    assert reopened.search("project-a", "unicorn") == []


def test_retry_and_exact_repetition(settings):
    store = MemoryStore(settings.db_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ingest(store, "p", "t", exchange()), range(4)))
    assert all(result == results[0] for result in results)
    repeated = ingest(store, "p", "another-thread", exchange(message_id="u2"))
    assert repeated == []
    assert len(store.search("p", "memory")) == 1
    assert len(store.inspect("p", results[0][0])["sources"]) == 2
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM completed_interactions").fetchone()[0] == 2


def test_failed_ingestion_is_atomic(settings):
    store = MemoryStore(settings.db_path)
    with pytest.raises(KeyError):
        ingest(store, "p", "t", [exchange()[0], {"role": "ai"}])
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM source_events").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM memory_notes").fetchone()[0] == 0
    assert ingest(store, "p", "t", exchange())


def test_budget_and_empty_query(settings):
    store = MemoryStore(settings.db_path)
    for index in range(12):
        ingest(store, "p", "t", exchange(f"memory research experiment number {index}", f"u{index}"))
    assert store.search("p", "") == []
    assert store.search("p", "memory", budget=1) == []
    selected = store.search("p", "memory", budget=2000)
    assert selected
    assert len(json.dumps(selected, ensure_ascii=False).encode()) <= 2000
    assert len(store.search("p", "memory", budget=100000, limit=100)) == 10


def test_unknown_memory_and_incomplete_interaction(settings):
    store = MemoryStore(settings.db_path)
    assert store.inspect("p", "invented-id") is None
    with pytest.raises(ValueError, match="completed"):
        ingest(store, "p", "t", exchange()[:1])


def test_completed_source_cannot_be_rewritten(settings):
    store = MemoryStore(settings.db_path)
    original = ingest(store, "p", "t", exchange())
    with pytest.raises(ValueError, match="different evidence"):
        ingest(store, "p", "t", exchange("Changed content with the same source ID"))
    assert store.inspect("p", original[0])["text"] == exchange()[0]["content"]
