"""Versioned SQLite memory with immutable evidence and transactional reconciliation."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from app.memory.embeddings import Embeddings
from app.memory.evolve import searchable
from app.memory.search import cosine, vector


def stable_id(*parts: str) -> str:
    return sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:32]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ConcurrentWriteError(RuntimeError):
    pass


class MemoryStore:
    def __init__(self, path: Path, *, embeddings=None):
        self.embeddings = embeddings or Embeddings()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise ValueError(f"Unsupported memory schema version: {version}")
            if version == 3:
                return
            if version == 2:
                self._migrate_graph(db)
                return
            if version == 1:
                db.execute("ALTER TABLE memory_notes RENAME TO legacy_notes")
            statements = [
                """CREATE TABLE IF NOT EXISTS source_events (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, thread_id TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    tool_name TEXT, source_location TEXT)""",
                """CREATE TABLE memory_notes (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL,
                    subject TEXT NOT NULL, origin TEXT NOT NULL,
                    current_version_id TEXT NOT NULL REFERENCES memory_versions(id)
                        DEFERRABLE INITIALLY DEFERRED,
                    recorded_at TEXT NOT NULL)""",
                """CREATE TABLE memory_versions (
                    id TEXT PRIMARY KEY, note_id TEXT NOT NULL REFERENCES memory_notes(id),
                    text TEXT NOT NULL, search_vector TEXT NOT NULL, status TEXT NOT NULL,
                    recorded_at TEXT NOT NULL, event_time TEXT)""",
                """CREATE TABLE version_sources (
                    version_id TEXT NOT NULL REFERENCES memory_versions(id),
                    source_id TEXT NOT NULL REFERENCES source_events(id),
                    PRIMARY KEY(version_id, source_id))""",
                """CREATE TABLE IF NOT EXISTS completed_interactions (
                    id TEXT PRIMARY KEY, note_ids TEXT NOT NULL, completed_at TEXT NOT NULL)""",
                """CREATE TABLE interaction_events (
                    interaction_id TEXT NOT NULL,
                    source_id TEXT NOT NULL REFERENCES source_events(id),
                    position INTEGER NOT NULL, PRIMARY KEY(interaction_id, position))""",
                """CREATE TABLE memory_operations (
                    id TEXT PRIMARY KEY, interaction_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    input_event_ids TEXT NOT NULL, action TEXT, target_note_ids TEXT NOT NULL,
                    reason TEXT NOT NULL, model_version TEXT NOT NULL, prompt_version TEXT NOT NULL,
                    status TEXT NOT NULL, recorded_at TEXT NOT NULL)""",
                """CREATE TABLE thread_summaries (
                    project_id TEXT NOT NULL, thread_id TEXT NOT NULL, text TEXT NOT NULL,
                    source_ids TEXT NOT NULL, updated_at TEXT NOT NULL,
                    observed_order INTEGER NOT NULL,
                    PRIMARY KEY(project_id, thread_id))""",
                """CREATE TABLE project_revisions (
                    project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL)""",
                "CREATE INDEX versions_note ON memory_versions(note_id)",
                "CREATE INDEX events_thread ON source_events(project_id, thread_id)",
                "CREATE INDEX operations_project ON memory_operations(project_id, interaction_id)",
            ]
            for statement in statements:
                db.execute(statement)
            if version == 1:
                db.execute("ALTER TABLE source_events ADD COLUMN tool_name TEXT")
                db.execute("ALTER TABLE source_events ADD COLUMN source_location TEXT")
                for note in db.execute("SELECT * FROM legacy_notes").fetchall():
                    version_id = stable_id(note["id"], "legacy-v1")
                    db.execute(
                        "INSERT INTO memory_notes VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            note["id"],
                            note["project_id"],
                            note["kind"],
                            "legacy user statement",
                            "user",
                            version_id,
                            note["recorded_at"],
                        ),
                    )
                    db.execute(
                        "INSERT INTO memory_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            version_id,
                            note["id"],
                            note["text"],
                            note["search_vector"],
                            "active",
                            note["recorded_at"],
                            None,
                        ),
                    )
                    db.execute(
                        """INSERT INTO version_sources SELECT ?, source_id FROM note_sources
                           WHERE note_id=?""",
                        (version_id, note["id"]),
                    )
                for done in db.execute("SELECT id FROM completed_interactions").fetchall():
                    events = db.execute(
                        """SELECT evidence.id FROM source_events evidence
                           JOIN source_events first ON first.id=?
                           WHERE evidence.project_id=first.project_id
                             AND evidence.thread_id=first.thread_id
                             AND evidence.recorded_at=first.recorded_at
                           ORDER BY evidence.rowid""",
                        (done["id"],),
                    ).fetchall()
                    db.executemany(
                        "INSERT INTO interaction_events VALUES (?, ?, ?)",
                        [
                            (done["id"], event["id"], position)
                            for position, event in enumerate(events)
                        ],
                    )
                db.execute("DROP TABLE note_sources")
                db.execute("DROP TABLE legacy_notes")
            db.execute("CREATE INDEX notes_project ON memory_notes(project_id)")
            self._migrate_graph(db)

    def _migrate_graph(self, db):
        db.execute("""CREATE TABLE embedding_cache (
            input_id TEXT PRIMARY KEY, embedding TEXT NOT NULL)""")
        db.execute("""CREATE TABLE note_metadata (
            version_id TEXT PRIMARY KEY REFERENCES memory_versions(id),
            metadata TEXT NOT NULL, embedding TEXT NOT NULL, embedding_space TEXT NOT NULL)""")
        db.execute("""CREATE TABLE metadata_history (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES memory_versions(id),
            interaction_id TEXT NOT NULL, metadata TEXT NOT NULL, source_ids TEXT NOT NULL,
            reason TEXT NOT NULL, recorded_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE memory_links (
            id TEXT PRIMARY KEY, from_version TEXT NOT NULL REFERENCES memory_versions(id),
            to_version TEXT NOT NULL REFERENCES memory_versions(id), relation TEXT NOT NULL,
            source_ids TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
            recorded_at TEXT NOT NULL)""")
        db.execute("CREATE INDEX links_from ON memory_links(from_version)")
        db.execute("CREATE INDEX links_to ON memory_links(to_version)")
        db.execute("PRAGMA user_version=3")

    def embedding_for(self, note):
        metadata = note.get("metadata", {"context": "", "keywords": [], "tags": []})
        if note.get("embedding_space") == self.embeddings.space:
            return json.loads(note["embedding"])
        text = searchable(note, metadata)
        input_id = stable_id(self.embeddings.space, text)
        with self.connection() as db:
            cached = db.execute(
                "SELECT embedding FROM embedding_cache WHERE input_id=?", (input_id,)
            ).fetchone()
        if cached:
            return json.loads(cached[0])
        embedding = self.embeddings.embed(text)
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO embedding_cache VALUES (?, ?)",
                (input_id, json.dumps(embedding)),
            )
        return embedding

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, project_id: str, thread_id: str, events: list[dict]) -> tuple[str, list[dict]]:
        if not events or events[0]["role"] != "human":
            raise ValueError("An interaction must start with its user source event")
        if events[-1]["role"] != "ai":
            raise ValueError("Only completed interactions may be ingested")
        if any(not event["id"] or not isinstance(event["content"], str) for event in events):
            raise ValueError("Source events require stable IDs and textual content")
        sources = [
            {
                "id": stable_id(project_id, thread_id, event["id"]),
                "role": event["role"],
                "content": event["content"],
                "tool_name": event.get("tool_name"),
                "source_location": event.get("source_location"),
            }
            for event in events
        ]
        source_ids = [event["id"] for event in sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("An interaction cannot reuse a source ID")
        interaction_id = source_ids[0]
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT source_id FROM interaction_events WHERE interaction_id=? ORDER BY position",
                (interaction_id,),
            ).fetchall()
            if previous and [row["source_id"] for row in previous] != source_ids:
                raise ValueError("An interaction cannot be retried with different evidence")
            for source in sources:
                existing = db.execute(
                    "SELECT * FROM source_events WHERE id=?",
                    (source["id"],),
                ).fetchone()
                if existing and any(
                    existing[key] != source[key]
                    for key in ("role", "content", "tool_name", "source_location")
                ):
                    raise ValueError("Source IDs cannot be reused for different evidence")
                db.execute(
                    "INSERT OR IGNORE INTO source_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        source["id"],
                        project_id,
                        thread_id,
                        source["role"],
                        source["content"],
                        now_iso(),
                        source["tool_name"],
                        source["source_location"],
                    ),
                )
            db.executemany(
                "INSERT OR IGNORE INTO interaction_events VALUES (?, ?, ?)",
                [
                    (interaction_id, source_id, position)
                    for position, source_id in enumerate(source_ids)
                ],
            )
        return interaction_id, self.sources(project_id, source_ids)

    def completed(self, interaction_id: str) -> list[str] | None:
        with self.connection() as db:
            done = db.execute(
                "SELECT note_ids FROM completed_interactions WHERE id=?",
                (interaction_id,),
            ).fetchone()
        return json.loads(done["note_ids"]) if done else None

    def snapshot(self, project_id: str, thread_id: str, interaction_id: str) -> dict:
        with self.connection() as db:
            db.execute("BEGIN")
            revision = db.execute(
                "SELECT revision FROM project_revisions WHERE project_id=?",
                (project_id,),
            ).fetchone()
            notes = db.execute(
                """SELECT n.*, v.text, v.search_vector,
                          (SELECT max(s.rowid) FROM source_events s JOIN version_sources evidence
                           ON evidence.source_id=s.id WHERE evidence.version_id=v.id)
                          AS evidence_order
                   FROM memory_notes n
                   JOIN memory_versions v ON v.id=n.current_version_id
                   WHERE n.project_id=? AND v.status='active' ORDER BY n.id""",
                (project_id,),
            ).fetchall()
            enriched = []
            for row in notes:
                note = dict(row)
                note["source_ids"] = [
                    source[0]
                    for source in db.execute(
                        "SELECT source_id FROM version_sources WHERE version_id=?",
                        (note["current_version_id"],),
                    )
                ]
                meta = db.execute(
                    "SELECT * FROM note_metadata WHERE version_id=?", (note["current_version_id"],)
                ).fetchone()
                if meta:
                    note.update(dict(meta))
                    note["metadata"] = json.loads(meta["metadata"])
                note["metadata_order"] = db.execute(
                    """SELECT coalesce(max(s.rowid), 0) FROM metadata_history h
                       JOIN json_each(h.source_ids) refs JOIN source_events s ON s.id=refs.value
                       WHERE h.version_id=?""",
                    (note["current_version_id"],),
                ).fetchone()[0]
                enriched.append(note)
            summary = db.execute(
                """SELECT text, source_ids FROM thread_summaries WHERE project_id=? AND thread_id=?
                   AND observed_order < (SELECT rowid FROM source_events WHERE id=?)""",
                (project_id, thread_id, interaction_id),
            ).fetchone()
            recent = db.execute(
                """SELECT * FROM source_events WHERE project_id=? AND thread_id=?
                   AND id NOT IN (SELECT source_id FROM interaction_events WHERE interaction_id=?)
                   AND rowid < (SELECT rowid FROM source_events WHERE id=?)
                   ORDER BY rowid DESC LIMIT 8""",
                (project_id, thread_id, interaction_id, interaction_id),
            ).fetchall()
        return {
            "revision": revision["revision"] if revision else 0,
            "notes": enriched,
            "summary": {"text": summary["text"], "source_ids": json.loads(summary["source_ids"])}
            if summary
            else {"text": "", "source_ids": []},
            "recent": [dict(event) for event in reversed(recent)],
        }

    def sources(self, project_id: str, source_ids: list[str]) -> list[dict]:
        with self.connection() as db:
            result = []
            for source_id in dict.fromkeys(source_ids):
                row = db.execute(
                    "SELECT *, rowid AS event_order FROM source_events WHERE id=? AND project_id=?",
                    (source_id, project_id),
                ).fetchone()
                if row:
                    result.append(dict(row))
        return result

    def commit(
        self,
        project_id,
        thread_id,
        interaction_id,
        revision,
        changes,
        summary,
        policy,
        graph_changes=None,
    ):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            done = db.execute(
                "SELECT note_ids FROM completed_interactions WHERE id=?",
                (interaction_id,),
            ).fetchone()
            if done:
                return json.loads(done["note_ids"])
            current = db.execute(
                "SELECT revision FROM project_revisions WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if (current["revision"] if current else 0) != revision:
                raise ConcurrentWriteError("Project memory changed during reconciliation")
            affected = []
            timestamp = now_iso()
            for position, change in enumerate(changes):
                candidate, decision, note_id = change
                target = None
                if decision.target_note_id:
                    target = db.execute(
                        "SELECT * FROM memory_notes WHERE id=? AND project_id=?",
                        (decision.target_note_id, project_id),
                    ).fetchone()
                    if target is None or any(
                        target[key] != getattr(candidate, key)
                        for key in ("kind", "subject", "origin")
                    ):
                        raise ValueError("Reconciliation target is incompatible with candidate")
                if decision.action == "NOOP":
                    if target:
                        db.executemany(
                            "INSERT OR IGNORE INTO version_sources VALUES (?, ?)",
                            [
                                (target["current_version_id"], source_id)
                                for source_id in candidate.source_ids
                            ],
                        )
                else:
                    version_id = stable_id(interaction_id, str(position), "version")
                    if decision.action == "ADD":
                        db.execute(
                            "INSERT INTO memory_notes VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                note_id,
                                project_id,
                                candidate.kind,
                                candidate.subject,
                                candidate.origin,
                                version_id,
                                timestamp,
                            ),
                        )
                    else:
                        db.execute(
                            "UPDATE memory_versions SET status=? WHERE id=?",
                            (
                                "corrected" if decision.action == "UPDATE" else "superseded",
                                target["current_version_id"],
                            ),
                        )
                        db.execute(
                            "UPDATE memory_notes SET current_version_id=? WHERE id=?",
                            (version_id, note_id),
                        )
                    db.execute(
                        "INSERT INTO memory_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            version_id,
                            note_id,
                            candidate.text,
                            json.dumps(vector(candidate.text)),
                            "active",
                            timestamp,
                            candidate.event_time,
                        ),
                    )
                    db.executemany(
                        "INSERT INTO version_sources VALUES (?, ?)",
                        [(version_id, source_id) for source_id in candidate.source_ids],
                    )
                    if target:
                        old = target["current_version_id"]
                        db.execute(
                            """UPDATE memory_links SET status='historical'
                                      WHERE from_version=? OR to_version=?""",
                            (old, old),
                        )
                        if decision.action == "SUPERSEDE":
                            db.execute(
                                "INSERT INTO memory_links VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    stable_id(version_id, old, "supersedes"),
                                    version_id,
                                    old,
                                    "supersedes",
                                    json.dumps(candidate.source_ids),
                                    decision.reason,
                                    "historical",
                                    timestamp,
                                ),
                            )
                    affected.append(note_id)
                db.execute(
                    "INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        stable_id(interaction_id, str(position), "operation"),
                        interaction_id,
                        project_id,
                        json.dumps(candidate.source_ids),
                        decision.action,
                        json.dumps([note_id] if note_id else []),
                        decision.reason,
                        policy.model_version,
                        policy.prompt_version,
                        "completed",
                        timestamp,
                    ),
                )
            if graph_changes:
                self._commit_graph(
                    db, project_id, interaction_id, graph_changes, affected, policy, timestamp
                )
            observed_order = db.execute(
                "SELECT rowid FROM source_events WHERE id=?",
                (interaction_id,),
            ).fetchone()[0]
            db.execute(
                """INSERT INTO thread_summaries VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, thread_id) DO UPDATE SET
                     text=excluded.text, source_ids=excluded.source_ids,
                     updated_at=excluded.updated_at, observed_order=excluded.observed_order
                   WHERE excluded.observed_order >= thread_summaries.observed_order""",
                (
                    project_id,
                    thread_id,
                    summary.text,
                    json.dumps(summary.source_ids),
                    timestamp,
                    observed_order,
                ),
            )
            affected = list(dict.fromkeys(affected))
            db.execute(
                "INSERT INTO completed_interactions VALUES (?, ?, ?)",
                (interaction_id, json.dumps(affected), timestamp),
            )
            db.execute(
                """INSERT INTO project_revisions VALUES (?, 1)
                   ON CONFLICT(project_id) DO UPDATE SET revision=revision+1""",
                (project_id,),
            )
        return affected

    def _commit_graph(self, db, project_id, interaction_id, graph, affected, policy, timestamp):
        endpoints = {
            row["id"]: row["current_version_id"]
            for row in db.execute(
                "SELECT id, current_version_id FROM memory_notes WHERE project_id=?",
                (project_id,),
            )
        }
        for note_id, update in graph["metadata"].items():
            version_id = endpoints[note_id]
            metadata = json.dumps(update["metadata"])
            db.execute(
                """INSERT INTO note_metadata VALUES (?, ?, ?, ?)
                          ON CONFLICT(version_id) DO UPDATE SET metadata=excluded.metadata,
                          embedding=excluded.embedding, embedding_space=excluded.embedding_space""",
                (version_id, metadata, json.dumps(update["embedding"]), self.embeddings.space),
            )
            db.execute(
                "INSERT INTO metadata_history VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    stable_id(interaction_id, note_id, "metadata"),
                    version_id,
                    interaction_id,
                    metadata,
                    json.dumps(update["source_ids"]),
                    update["reason"],
                    timestamp,
                ),
            )
            action = "ENRICH" if note_id in affected else "EVOLVE"
            db.execute(
                "INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    stable_id(interaction_id, note_id, "metadata-operation"),
                    interaction_id,
                    project_id,
                    json.dumps(update["source_ids"]),
                    action,
                    json.dumps([note_id]),
                    update["reason"],
                    policy.model_version,
                    policy.prompt_version,
                    "completed",
                    timestamp,
                ),
            )
            affected.append(note_id)
        for link in graph["links"]:
            left, right = endpoints[link["from"]], endpoints[link["target_note_id"]]
            db.execute(
                "INSERT OR IGNORE INTO memory_links VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    stable_id(left, right, link["relation"]),
                    left,
                    right,
                    link["relation"],
                    json.dumps(link["source_ids"]),
                    link["reason"],
                    "active",
                    timestamp,
                ),
            )

            db.execute(
                "INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    stable_id(interaction_id, left, right, link["relation"], "link-operation"),
                    interaction_id,
                    project_id,
                    json.dumps(link["source_ids"]),
                    "LINK",
                    json.dumps([link["from"], link["target_note_id"]]),
                    link["reason"],
                    policy.model_version,
                    policy.prompt_version,
                    "completed",
                    timestamp,
                ),
            )

    def record_failure(self, project_id, interaction_id, sources, policy, error):
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO memory_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    stable_id(interaction_id, "failed", type(error).__name__),
                    interaction_id,
                    project_id,
                    json.dumps([source["id"] for source in sources]),
                    None,
                    "[]",
                    f"Consolidation failed: {type(error).__name__}; evidence retained for retry",
                    policy.model_version,
                    policy.prompt_version,
                    "failed",
                    now_iso(),
                ),
            )

    def inspect(self, project_id: str, note_id: str) -> dict | None:
        with self.connection() as db:
            note = db.execute(
                "SELECT * FROM memory_notes WHERE id=? AND project_id=?",
                (note_id, project_id),
            ).fetchone()
            if note is None:
                return None
            versions = db.execute(
                """SELECT id AS version_id, text, status, recorded_at, event_time
                   FROM memory_versions WHERE note_id=? ORDER BY rowid""",
                (note_id,),
            ).fetchall()
            history = []
            for version in versions:
                sources = db.execute(
                    """SELECT s.* FROM source_events s JOIN version_sources evidence
                       ON evidence.source_id=s.id WHERE evidence.version_id=? AND s.project_id=?
                       ORDER BY s.recorded_at, s.id""",
                    (version["version_id"], project_id),
                ).fetchall()
                history.append({**dict(version), "sources": [dict(source) for source in sources]})
            for version in history:
                meta = db.execute(
                    "SELECT metadata FROM note_metadata WHERE version_id=?",
                    (version["version_id"],),
                ).fetchone()
                version["metadata"] = json.loads(meta[0]) if meta else None
                version["metadata_history"] = [
                    {
                        **dict(row),
                        "metadata": json.loads(row["metadata"]),
                        "source_ids": json.loads(row["source_ids"]),
                    }
                    for row in db.execute(
                        "SELECT * FROM metadata_history WHERE version_id=? ORDER BY rowid",
                        (version["version_id"],),
                    )
                ]
            connections = [
                {**dict(row), "source_ids": json.loads(row["source_ids"])}
                for row in db.execute(
                    """SELECT l.*, a.note_id AS from_note_id, b.note_id AS to_note_id
                       FROM memory_links l JOIN memory_versions a ON a.id=l.from_version
                       JOIN memory_versions b ON b.id=l.to_version
                       JOIN memory_notes na ON na.id=a.note_id
                       JOIN memory_notes nb ON nb.id=b.note_id
                       WHERE (a.note_id=? OR b.note_id=?) AND na.project_id=? AND nb.project_id=?
                       ORDER BY l.id""",
                    (note_id, note_id, project_id, project_id),
                )
            ]
            operations = db.execute(
                "SELECT * FROM memory_operations WHERE project_id=? ORDER BY rowid",
                (project_id,),
            ).fetchall()
        current = next(item for item in history if item["version_id"] == note["current_version_id"])
        return {
            **dict(note),
            **current,
            "versions": history,
            "connections": connections,
            "operations": [
                {
                    **dict(operation),
                    "input_event_ids": json.loads(operation["input_event_ids"]),
                    "target_note_ids": json.loads(operation["target_note_ids"]),
                }
                for operation in operations
                if note_id in json.loads(operation["target_note_ids"])
            ],
        }

    def search(
        self,
        project_id: str,
        query: str,
        budget: int = 2000,
        limit: int = 10,
        include_history: bool = False,
    ) -> list[dict]:
        if budget <= 0 or limit <= 0 or not query.strip():
            return []
        query_vector = self.embeddings.embed(query, query=True)
        with self.connection() as db:
            rows = db.execute(
                """SELECT n.id, n.kind, n.subject, n.origin, v.id AS version_id,
                          v.text, v.status, v.recorded_at, v.event_time,
                          m.metadata, m.embedding, m.embedding_space
                   FROM memory_notes n JOIN memory_versions v ON v.note_id=n.id
                   LEFT JOIN note_metadata m ON m.version_id=v.id
                   WHERE n.project_id=? AND (? OR v.status='active')""",
                (project_id, include_history),
            ).fetchall()
            notes, scores = {}, {}
            for row in rows:
                note = dict(row)
                note["metadata"] = (
                    json.loads(note["metadata"])
                    if note["metadata"]
                    else {
                        "context": "",
                        "keywords": [],
                        "tags": [],
                    }
                )
                embedding = self.embedding_for(note)
                if self.embeddings.model != "demo:lexical" and set(embedding) != set(query_vector):
                    raise ValueError("Embedding dimensions changed within the configured space")
                scores[note["version_id"]] = max(0.0, cosine(query_vector, embedding))
                del note["embedding"], note["embedding_space"]
                notes[note["version_id"]] = note
            direct = sorted(
                (key for key in notes if scores[key] > 0), key=lambda key: (-scores[key], key)
            )[:10]
            linked = {}
            for seed in direct:
                for row in db.execute(
                    """SELECT * FROM memory_links WHERE (from_version=? OR to_version=?)
                       AND (? OR status='active') ORDER BY id""",
                    (seed, seed, include_history),
                ):
                    target = (
                        row["to_version"] if row["from_version"] == seed else row["from_version"]
                    )
                    if target not in notes or target == seed:
                        continue
                    strength = scores[seed]
                    if target not in linked or strength > linked[target][0]:
                        linked[target] = (strength, seed, row["relation"])
            expansion = sorted(
                (key for key in linked if key not in direct),
                key=lambda key: (-linked[key][0], -scores[key], key),
            )[:10]
            candidates = set(direct) | set(expansion)

            def rank(key):
                return (
                    0.8 * scores[key]
                    + 0.15 * linked.get(key, (0,))[0]
                    + 0.05 * (notes[key]["status"] == "active")
                )

            selected = []
            for key in sorted(candidates, key=lambda key: (-rank(key), key)):
                if len(selected) >= min(limit, 10):
                    break
                note = notes[key]
                sources = db.execute(
                    """SELECT s.id, s.role, s.content FROM source_events s
                       JOIN version_sources evidence ON evidence.source_id=s.id
                       WHERE evidence.version_id=? AND s.project_id=?
                       ORDER BY s.recorded_at, s.id LIMIT 3""",
                    (key, project_id),
                ).fetchall()
                metadata_sources = db.execute(
                    "SELECT source_ids FROM metadata_history WHERE version_id=? "
                    "ORDER BY rowid DESC LIMIT 1",
                    (key,),
                ).fetchone()
                note["metadata_source_ids"] = (
                    json.loads(metadata_sources[0]) if metadata_sources else []
                )
                note["sources"] = [
                    {"id": source["id"], "role": source["role"], "excerpt": source["content"][:200]}
                    for source in sources
                ]
                mode = "lexical demo" if self.embeddings.model == "demo:lexical" else "semantic"
                note.update(
                    score=round(rank(key), 6),
                    similarity=round(scores[key], 6),
                    reason=f"direct {mode} match" if key in direct else "one-hop link",
                    retrieval="direct" if key in direct else "linked",
                )
                if key in linked:
                    note["via"] = {"version_id": linked[key][1], "relation": linked[key][2]}
                if len(json.dumps([*selected, note], ensure_ascii=False).encode()) <= budget:
                    selected.append(note)
        return selected
