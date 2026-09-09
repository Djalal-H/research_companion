import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.memory.extract import ModelPolicy, ScriptedPolicy
from app.memory.prompts import EXTRACT, INPUT_BUDGET
from app.memory.reconcile import MemoryEngine, extraction_context, serialized_size
from app.memory.schemas import Candidate, Decision, Extraction, Summary
from app.memory.search import vector
from app.memory.store import MemoryStore, stable_id


def exchange(text, message_id="user"):
    return [
        {"id": message_id, "role": "human", "content": text},
        {"id": f"assistant-{message_id}", "role": "ai", "content": "Acknowledged."},
    ]


class ControlledPolicy(ScriptedPolicy):
    def __init__(self, extract=None, reconcile=None):
        self.extract_override = extract
        self.reconcile_override = reconcile

    def extract(self, context):
        return self.extract_override(context) if self.extract_override else super().extract(context)

    def reconcile(self, candidate, neighbors, context):
        if self.reconcile_override:
            return self.reconcile_override(candidate, neighbors, context)
        return super().reconcile(candidate, neighbors, context)


def test_changes_corrections_and_historical_sources(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ScriptedPolicy())
    note_id = engine.ingest("p", "first", exchange("I have four weeks for research."))[0]
    original = store.inspect("p", note_id)
    assert engine.ingest("p", "second", exchange("I now have one week for research.")) == [note_id]
    assert not store.search("p", "four weeks")
    historical = store.search("p", "four weeks", include_history=True)
    assert historical[0]["version_id"] == original["version_id"]
    assert historical[0]["status"] == "superseded"
    engine.ingest("p", "third", exchange("Correction: I meant two days for research."))
    reopened = MemoryStore(settings.db_path)
    note = reopened.inspect("p", note_id)
    assert [version["status"] for version in note["versions"]] == [
        "superseded",
        "corrected",
        "active",
    ]
    assert note["versions"][0]["sources"] == original["sources"]
    assert note["text"] == "Correction: I meant two days for research."
    assert [
        operation["action"]
        for operation in note["operations"]
        if operation["action"] not in {"ENRICH", "EVOLVE"}
    ] == [
        "ADD",
        "SUPERSEDE",
        "UPDATE",
    ]
    assert all(
        operation["reason"] and operation["model_version"] for operation in note["operations"]
    )
    assert reopened.search("other", "research", include_history=True) == []
    with store.connection() as db:
        active = db.execute(
            "SELECT search_vector FROM memory_versions WHERE status='active'"
        ).fetchone()
    assert json.loads(active[0]) == vector(note["text"])


def test_paraphrase_noop_preserves_additional_evidence(settings):
    store = MemoryStore(settings.db_path)
    original = MemoryEngine(store, ScriptedPolicy()).ingest("p", "t", exchange("I have one week."))[
        0
    ]
    policy = ControlledPolicy(
        reconcile=lambda candidate, notes, context: Decision(
            action="NOOP",
            target_note_id=notes[0]["id"],
            reason="Seven days means one week",
        )
    )
    assert MemoryEngine(store, policy).ingest("p", "t2", exchange("My budget is seven days.")) == []
    note = store.inspect("p", original)
    assert len(note["versions"]) == 1
    assert len(note["sources"]) == 2
    assert note["operations"][-1]["action"] == "NOOP"
    assert note["sources"][1]["content"] == "My budget is seven days."


def test_ambiguous_conflicts_remain_active(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ScriptedPolicy())
    engine.ingest("p", "t1", exchange("I have one week."))
    engine.ingest("p", "t2", exchange("I have two weeks."))
    with store.connection() as db:
        assert (
            db.execute("SELECT count(*) FROM memory_versions WHERE status='active'").fetchone()[0]
            == 2
        )


@pytest.mark.parametrize("changed", ["human", "ai", "tool", "removed", "metadata"])
def test_retry_validates_all_evidence(settings, changed):
    engine = MemoryEngine(MemoryStore(settings.db_path), ScriptedPolicy())
    events = exchange("I have one week.")
    events.insert(
        1, {"id": "tool", "role": "tool", "content": "paper evidence", "tool_name": "read_paper"}
    )
    engine.ingest("p", "t", events)
    if changed == "removed":
        events.pop(1)
    elif changed == "metadata":
        events[1]["tool_name"] = "search_papers"
    else:
        next(event for event in events if event["role"] == changed)["content"] = "changed"
    with pytest.raises(ValueError, match="different evidence"):
        engine.ingest("p", "t", events)


def test_invalid_model_output_retains_evidence_and_retry_after_restart(settings):
    store = MemoryStore(settings.db_path)
    events = exchange("I have one week.")
    policy = ControlledPolicy(extract=lambda context: {"candidates": "malformed"})
    with pytest.raises(ValueError):
        MemoryEngine(store, policy).ingest("p", "t", events)
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM source_events").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM memory_versions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM thread_summaries").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM completed_interactions").fetchone()[0] == 0
        assert db.execute("SELECT status FROM memory_operations").fetchone()[0] == "failed"
    reopened = MemoryStore(settings.db_path)
    recovered = MemoryEngine(reopened, ScriptedPolicy())
    interaction_id = stable_id("p", "t", "user")
    ids = recovered.retry("p", "t", interaction_id)
    assert ids == recovered.ingest("p", "t", events)
    assert len(reopened.search("p", "one week")) == 1
    with pytest.raises(ValueError, match="Unknown interaction"):
        recovered.retry("other", "t", interaction_id)


def test_delayed_retry_cannot_replace_newer_fact_or_thread_summary(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ScriptedPolicy())
    note_id = engine.ingest("p", "t", exchange("I have four weeks.", "first"))[0]
    earlier = exchange("I now have two weeks.", "earlier")
    interaction_id, _sources = store.record("p", "t", earlier)
    engine.ingest("p", "t", exchange("I now have one week.", "later"))
    with store.connection() as db:
        summary = dict(db.execute("SELECT * FROM thread_summaries").fetchone())
    assert engine.retry("p", "t", interaction_id) == []
    assert store.inspect("p", note_id)["text"] == "I now have one week."
    assert len(store.inspect("p", note_id)["versions"]) == 2
    with store.connection() as db:
        assert dict(db.execute("SELECT * FROM thread_summaries").fetchone()) == summary


def test_commit_failure_rolls_back_versions_and_can_retry(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ScriptedPolicy())
    note_id = engine.ingest("p", "t", exchange("I have four weeks.", "first"))[0]
    with store.connection() as db:
        db.execute("""CREATE TRIGGER fail_completion BEFORE INSERT ON completed_interactions
                   BEGIN SELECT RAISE(ABORT, 'simulated interruption'); END""")
    events = exchange("I now have one week.", "changed")
    with pytest.raises(sqlite3.IntegrityError, match="simulated interruption"):
        engine.ingest("p", "t", events)
    assert store.inspect("p", note_id)["text"] == "I have four weeks."
    assert len(store.inspect("p", note_id)["versions"]) == 1
    with store.connection() as db:
        db.execute("DROP TRIGGER fail_completion")
    assert engine.retry("p", "t", stable_id("p", "t", "changed")) == [note_id]


@pytest.mark.parametrize(
    "attack", ["invented", "cross_project", "assistant_decision", "fake_paper"]
)
def test_invalid_provenance_is_rejected(settings, attack):
    store = MemoryStore(settings.db_path)
    MemoryEngine(store, ScriptedPolicy()).ingest("other", "t", exchange("Private statement."))

    def extract(context):
        source_id = context["current"][0]["id"]
        origin, kind = "user", "decision"
        if attack == "invented":
            source_id = "invented"
        elif attack == "cross_project":
            source_id = stable_id("other", "t", "user")
        elif attack == "assistant_decision":
            source_id = context["current"][-1]["id"]
        elif attack == "fake_paper":
            origin, kind = "paper", "finding"
        return Extraction(
            candidates=[
                Candidate(
                    text="Unsupported claim",
                    subject="experiment",
                    kind=kind,
                    origin=origin,
                    source_ids=[source_id],
                )
            ],
            summary=Summary(text=""),
        )

    with pytest.raises(ValueError):
        MemoryEngine(store, ControlledPolicy(extract=extract)).ingest(
            "p", "t", exchange("Discuss.")
        )
    assert store.search("p", "claim") == []


def test_proposal_acceptance_and_paper_preference_separation(settings):
    store = MemoryStore(settings.db_path)

    def extract(context):
        sources = context["current"]
        return Extraction(
            candidates=[
                Candidate(
                    text="Use baseline A",
                    subject="experiment",
                    kind="proposal",
                    origin="assistant",
                    source_ids=[sources[-1]["id"]],
                ),
                Candidate(
                    text="Use baseline A",
                    subject="experiment",
                    kind="decision",
                    origin="user",
                    source_ids=[sources[0]["id"]],
                ),
                Candidate(
                    text="Paper measures retrieval",
                    subject="research objective",
                    kind="finding",
                    origin="paper",
                    source_ids=[sources[1]["id"]],
                ),
            ],
            summary=Summary(text=""),
        )

    events = exchange("I accept baseline A.")
    events[-1]["content"] = "I suggest baseline A."
    events.insert(
        1,
        {
            "id": "paper",
            "role": "tool",
            "content": "Paper measures retrieval",
            "tool_name": "read_paper",
            "source_location": "paper:amem:S2",
        },
    )
    ids = MemoryEngine(store, ControlledPolicy(extract=extract)).ingest("p", "t", events)
    assert len(ids) == 3
    engine = MemoryEngine(store, ScriptedPolicy())
    engine.ingest("p", "t2", exchange("I am interested in retrieval quality."))
    engine.ingest("p", "t3", exchange("Let's focus on changing facts instead."))
    assert store.inspect("p", ids[2])["text"] == "Paper measures retrieval"
    assert store.inspect("p", ids[0])["kind"] == "proposal"
    assert store.inspect("p", ids[1])["kind"] == "decision"


def test_invalid_later_decision_leaves_previous_valid_state(settings):
    store = MemoryStore(settings.db_path)
    original = MemoryEngine(store, ScriptedPolicy()).ingest(
        "p", "t", exchange("I have four weeks.")
    )[0]

    def reconcile(candidate, notes, context):
        if candidate.kind == "constraint":
            return Decision(action="SUPERSEDE", target_note_id=original, reason="Changed time")
        return Decision(action="UPDATE", target_note_id="invented", reason="Invalid target")

    with pytest.raises(ValueError, match="target"):
        MemoryEngine(store, ControlledPolicy(reconcile=reconcile)).ingest(
            "p",
            "t2",
            exchange("I now have one week. I focus on changing facts."),
        )
    assert store.inspect("p", original)["text"] == "I have four weeks."
    assert len(store.inspect("p", original)["versions"]) == 1


def test_concurrent_new_interactions_reconcile_again(settings):
    store = MemoryStore(settings.db_path)
    barrier = Barrier(2)

    class RacingPolicy(ScriptedPolicy):
        def __init__(self):
            self.calls = 0

        def extract(self, context):
            self.calls += 1
            if self.calls == 1:
                barrier.wait(timeout=10)
            return super().extract(context)

    policies = [RacingPolicy(), RacingPolicy()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                MemoryEngine(store, policy).ingest, "p", f"t{index}", exchange("I have one week.")
            )
            for index, policy in enumerate(policies)
        ]
        results = [future.result() for future in futures]
    assert sorted(map(len, results)) == [0, 1]
    assert sorted(policy.calls for policy in policies) == [1, 2]
    note = store.search("p", "one week")[0]
    assert len(store.inspect("p", note["id"])["sources"]) == 2


def test_extraction_context_is_bounded_and_summary_is_thread_local(settings):
    store = MemoryStore(settings.db_path)
    engine = MemoryEngine(store, ScriptedPolicy())
    for index in range(7):
        engine.ingest("p", "t", exchange(f"Research finding {index}.", str(index)))
    events = exchange("I have one week.", "latest")
    events.insert(1, {"id": "large", "role": "tool", "content": "evidence " * 20000})
    interaction_id, sources = store.record("p", "t", events)
    snapshot = store.snapshot("p", "t", interaction_id)
    context = extraction_context(snapshot, sources)
    assert len(context["recent"]) <= 8
    assert serialized_size(context) + len(EXTRACT) <= INPUT_BUDGET
    assert len(context["summary"]["text"]) <= 2000
    assert any(event["truncated"] for event in context["current"])
    assert len(store.sources("p", [sources[1]["id"]])[0]["content"]) == 180000
    assert store.snapshot("p", "fresh", interaction_id)["summary"]["text"] == ""


def test_model_policy_uses_structured_outputs_and_disables_streaming():
    from langgraph.constants import TAG_NOSTREAM

    class FakeStructuredModel:
        def with_structured_output(self, schema):
            from app.memory.schemas import Enrichment

            assert schema in (Extraction, Decision, Enrichment)
            return self

        def invoke(self, messages, config):
            assert TAG_NOSTREAM in config["tags"]
            assert len(messages[0].text) + len(messages[1].text) <= INPUT_BUDGET
            return {"candidates": [], "summary": {"text": "", "source_ids": []}}

    result = ModelPolicy(FakeStructuredModel(), "fake").extract({"current": []})
    assert result.candidates == []


def test_retry_command_lists_and_consolidates_pending_work(settings, monkeypatch, capsys):
    from app.memory import retry

    store = MemoryStore(settings.db_path)
    interaction_id, _sources = store.record(settings.project_id, "t", exchange("I have one week."))
    monkeypatch.setattr(retry.Settings, "from_env", lambda: settings)
    monkeypatch.setattr("sys.argv", ["memory.retry"])
    retry.main()
    pending = json.loads(capsys.readouterr().out)
    assert pending[0]["interaction_id"] == interaction_id
    monkeypatch.setattr(
        "sys.argv",
        [
            "memory.retry",
            "--thread-id",
            "t",
            "--interaction-id",
            interaction_id,
        ],
    )
    retry.main()
    result = json.loads(capsys.readouterr().out)
    assert result["memory_status"] == "ready"
    assert store.inspect(settings.project_id, result["memory_changes"][0])["kind"] == "constraint"


def test_v1_migration_preserves_ids_sources_and_completion(settings):
    events = exchange("I have one week.")
    source_id = stable_id("p", "t", "user")
    assistant_id = stable_id("p", "t", "assistant-user")
    note_id = stable_id("p", "user_statement", events[0]["content"])
    with sqlite3.connect(settings.db_path) as db:
        db.executescript("""
            CREATE TABLE source_events (id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                thread_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                recorded_at TEXT NOT NULL);
            CREATE TABLE memory_notes (id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL, kind TEXT NOT NULL,
                text TEXT NOT NULL, search_vector TEXT NOT NULL, recorded_at TEXT NOT NULL);
            CREATE INDEX notes_project ON memory_notes(project_id);
            CREATE TABLE note_sources (note_id TEXT REFERENCES memory_notes(id),
                source_id TEXT REFERENCES source_events(id), PRIMARY KEY(note_id, source_id));
            CREATE TABLE completed_interactions (id TEXT PRIMARY KEY, note_ids TEXT NOT NULL,
                completed_at TEXT NOT NULL);
            PRAGMA user_version=1;
        """)
        for event_id, event in zip([source_id, assistant_id], events, strict=True):
            db.execute(
                "INSERT INTO source_events VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, "p", "t", event["role"], event["content"], "2026-01-01"),
            )
        db.execute(
            "INSERT INTO memory_notes VALUES (?, ?, ?, ?, ?, ?)",
            (
                note_id,
                "p",
                "user_statement",
                events[0]["content"],
                json.dumps(vector(events[0]["content"])),
                "2026-01-01",
            ),
        )
        db.execute("INSERT INTO note_sources VALUES (?, ?)", (note_id, source_id))
        db.execute(
            "INSERT INTO completed_interactions VALUES (?, ?, ?)",
            (source_id, json.dumps([note_id]), "2026-01-01"),
        )
    store = MemoryStore(settings.db_path)
    assert MemoryEngine(store, ScriptedPolicy()).ingest("p", "t", events) == [note_id]
    note = MemoryStore(settings.db_path).inspect("p", note_id)
    assert note["kind"] == "user_statement"
    assert note["sources"][0]["id"] == source_id
    assert len(note["versions"]) == 1
    with store.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
