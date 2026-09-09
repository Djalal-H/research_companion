import json
import math

import pytest
from test_memory import exchange

from app.memory.embeddings import Embeddings
from app.memory.extract import ScriptedPolicy
from app.memory.reconcile import MemoryEngine
from app.memory.schemas import Enrichment, Evolution, LinkProposal, Metadata
from app.memory.store import MemoryStore


class FixtureEmbeddings:
    """Controlled geometry, not a claim about a live embedding model."""

    space = model = "fixture:semantic-v1"

    def __init__(self):
        self.inputs = []

    def embed(self, text, *, query=False):
        self.inputs.append(text)
        if text.startswith(("anchor", "query")):
            return {"0": 1.0, "1": 0.0}
        if text.startswith("hidden"):
            return {"0": 0.0, "1": 1.0}
        return {"0": 0.1, "1": math.sqrt(0.99)}


class ConnectedPolicy(ScriptedPolicy):
    def enrich(self, context):
        result = super().enrich(context)
        if context["note"]["text"].startswith("anchor"):
            target = next(n for n in context["neighbors"] if n["text"].startswith("hidden"))
            refs = context["note"]["source_ids"] + target["source_ids"]
            result.links = [
                LinkProposal(
                    target_note_id=target["id"],
                    relation="explains",
                    source_ids=refs,
                    reason="Fixture supporting connection",
                )
            ]
            result.evolutions = [
                Evolution(
                    target_note_id=target["id"],
                    metadata=Metadata(
                        context="Relevant to the anchor finding",
                        keywords=["support"],
                        tags=["finding", "user"],
                    ),
                    source_ids=refs,
                    reason="New finding supplies experiment context",
                )
            ]
        return result


def test_evolution_preserves_facts_refreshes_vectors_and_survives_restart(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ConnectedPolicy())
    hidden = engine.ingest("p", "old", exchange("hidden evidence."))[0]
    original = store.inspect("p", hidden)
    with store.connection() as db:
        old_vector = db.execute("SELECT embedding FROM note_metadata").fetchone()[0]
    changes = engine.ingest("p", "new", exchange("anchor finding."))
    assert hidden in changes
    reopened = MemoryStore(settings.db_path)
    evolved = reopened.inspect("p", hidden)
    assert evolved["text"] == original["text"]
    assert evolved["sources"] == original["sources"]
    assert evolved["version_id"] == original["version_id"]
    assert len(evolved["versions"]) == 1
    assert len(evolved["metadata_history"]) == 2
    assert "EVOLVE" in [op["action"] for op in evolved["operations"]]
    assert evolved["connections"][0]["relation"] == "explains"
    with reopened.connection() as db:
        refreshed = db.execute(
            "SELECT embedding FROM note_metadata WHERE version_id=?", (evolved["version_id"],)
        ).fetchone()[0]
        assert refreshed != old_vector
    assert engine.ingest("p", "new", exchange("anchor finding.")) == changes
    assert len(reopened.inspect("p", hidden)["metadata_history"]) == 2
    assert "embedding" not in json.dumps(evolved)


def test_linked_candidate_competes_before_truncation(settings):
    embeddings = FixtureEmbeddings()
    store = MemoryStore(settings.db_path, embeddings=embeddings)
    engine = MemoryEngine(store, ConnectedPolicy())
    hidden = engine.ingest("p", "hidden", exchange("hidden evidence."))[0]
    anchor = engine.ingest("p", "anchor", exchange("anchor finding."))[0]
    for index in range(11):
        engine.ingest("p", f"f{index}", exchange(f"filler {index}."))
    recalled = store.search("p", "query", budget=20000, limit=2)
    assert [n["id"] for n in recalled] == [anchor, hidden]
    assert recalled[1]["retrieval"] == "linked"
    assert recalled[1]["similarity"] == 0
    assert recalled[1]["via"]["relation"] == "explains"
    assert store.search("other", "query") == []
    packed = store.search("p", "query", budget=2000)
    assert len(json.dumps(packed, ensure_ascii=False).encode()) <= 2000
    assert hidden in [n["id"] for n in packed]
    assert store.search("p", "query", budget=1) == []


def test_invalid_graph_output_rolls_back_and_retry_succeeds(settings):
    class Invalid(ConnectedPolicy):
        def enrich(self, context):
            result = super().enrich(context)
            if result.links:
                result.links[0].source_ids = ["invented"]
            return result

    store = MemoryStore(settings.db_path)
    hidden = MemoryEngine(store, ScriptedPolicy()).ingest("p", "old", exchange("hidden."))[0]
    before = store.inspect("p", hidden)
    with pytest.raises(ValueError, match="both endpoints"):
        MemoryEngine(store, Invalid()).ingest("p", "new", exchange("anchor."))
    assert store.inspect("p", hidden) == before
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM memory_notes").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM completed_interactions").fetchone()[0] == 1
    assert MemoryEngine(store, ConnectedPolicy()).ingest("p", "new", exchange("anchor."))


def test_superseded_links_excluded_from_current_recall(settings):
    class Constraints(ConnectedPolicy):
        def extract(self, context):
            result = super().extract(context)
            for candidate in result.candidates:
                candidate.kind = "constraint"
                candidate.subject = "time budget"
            return result

    store = MemoryStore(settings.db_path, embeddings=FixtureEmbeddings())
    engine = MemoryEngine(store, Constraints())
    hidden = engine.ingest("p", "a", exchange("hidden old fact."))[0]
    engine.ingest("p", "b", exchange("anchor evidence."))
    # Explicit targeted reconciliation avoids ambiguous conflicting fixture constraints.
    from app.memory.schemas import Decision

    class Replace(Constraints):
        def reconcile(self, candidate, neighbors, context):
            return Decision(action="SUPERSEDE", target_note_id=hidden, reason="Changed constraint")

    MemoryEngine(store, Replace()).ingest("p", "c", exchange("replacement fact."))
    current = store.search("p", "query", budget=20000)
    assert all(n["text"] != "hidden old fact." for n in current)
    historical = store.search("p", "query", budget=20000, include_history=True)
    assert any(n["text"] == "hidden old fact." for n in historical)
    assert all(link["status"] == "historical" for link in store.inspect("p", hidden)["connections"])


def test_v2_migration_does_not_reinterpret_existing_facts(settings):
    store = MemoryStore(settings.db_path)
    ids = MemoryEngine(store, ScriptedPolicy()).ingest("p", "t", exchange())
    with store.connection() as db:
        for table in ("memory_links", "metadata_history", "note_metadata", "embedding_cache"):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=2")
    reopened = MemoryStore(settings.db_path)
    assert reopened.inspect("p", ids[0])["metadata"] is None
    assert reopened.search("p", "one week")[0]["id"] == ids[0]
    assert MemoryEngine(reopened, ScriptedPolicy()).ingest("p", "t", exchange()) == ids


def test_embedding_adapter_validates_and_normalizes():
    class Client:
        def embed_documents(self, texts):
            return [[3.0, 4.0]]

        def embed_query(self, text):
            return [float("nan")]

    adapter = Embeddings("openai:fixture")
    adapter._client = Client()
    assert adapter.embed("text") == {"0": 0.6, "1": 0.8}
    with pytest.raises(ValueError, match="finite"):
        adapter.embed("query", query=True)


def test_structured_enrichment_is_bounded():
    with pytest.raises(ValueError):
        Enrichment(metadata=Metadata(context="x", keywords=["x" * 61], tags=[]))


def test_embedding_space_switch_reindexes_and_caches_without_fact_changes(settings):
    store = MemoryStore(settings.db_path)
    note_id = MemoryEngine(store, ScriptedPolicy()).ingest("p", "t", exchange("anchor."))[0]
    before = store.inspect("p", note_id)
    embeddings = FixtureEmbeddings()
    switched = MemoryStore(settings.db_path, embeddings=embeddings)
    assert switched.search("p", "query")[0]["id"] == note_id
    assert any(text.startswith("anchor") for text in embeddings.inputs)
    embeddings.inputs.clear()
    reopened = MemoryStore(settings.db_path, embeddings=embeddings)
    assert reopened.search("p", "query")[0]["id"] == note_id
    assert embeddings.inputs == ["query"]
    assert reopened.inspect("p", note_id) == before


def test_older_retry_cannot_overwrite_newer_metadata(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ConnectedPolicy())
    hidden = engine.ingest("p", "first", exchange("hidden evidence."))[0]
    pending, _ = store.record("p", "delayed", exchange("anchor earlier finding."))
    engine.ingest("p", "newer", exchange("anchor later finding."))
    before = store.inspect("p", hidden)["metadata_history"]
    engine.retry("p", "delayed", pending)
    assert store.inspect("p", hidden)["metadata_history"] == before


def test_database_failure_rolls_back_graph_and_fact_write(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ConnectedPolicy())
    hidden = engine.ingest("p", "first", exchange("hidden evidence."))[0]
    before = store.inspect("p", hidden)
    with store.connection() as db:
        db.execute("""CREATE TRIGGER fail_graph BEFORE INSERT ON memory_links
                      BEGIN SELECT RAISE(ABORT, 'simulated link storage failure'); END""")
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError, match="simulated"):
        engine.ingest("p", "next", exchange("anchor evidence."))
    assert store.inspect("p", hidden) == before
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM memory_notes").fetchone()[0] == 1
        db.execute("DROP TRIGGER fail_graph")
    assert engine.ingest("p", "next", exchange("anchor evidence."))
