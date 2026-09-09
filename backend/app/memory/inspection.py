"""Allowlisted browser payloads, derived exclusively from persisted memory."""

import json

from pydantic import BaseModel, Field

from app.memory.schemas import Metadata


class Evidence(BaseModel):
    id: str
    role: str
    content: str
    recorded_at: str
    thread_id: str
    tool_name: str | None = None
    source_location: str | None = None


class Operation(BaseModel):
    id: str
    interaction_id: str
    action: str | None
    target_note_ids: list[str]
    input_event_ids: list[str]
    reason: str
    status: str
    recorded_at: str


class MetadataRevision(BaseModel):
    id: str
    interaction_id: str
    metadata: Metadata
    source_ids: list[str]
    reason: str
    recorded_at: str


class Version(BaseModel):
    version_id: str
    text: str
    status: str
    recorded_at: str
    event_time: str | None
    sources: list[Evidence]
    metadata: Metadata | None
    metadata_history: list[MetadataRevision]


class Connection(BaseModel):
    id: str
    from_note_id: str
    to_note_id: str
    from_version: str
    to_version: str
    relation: str
    status: str
    reason: str
    source_ids: list[str]
    neighbor_id: str
    neighbor_text: str
    neighbor_version_id: str
    neighbor_status: str


class NoteDetail(BaseModel):
    id: str
    project_id: str
    kind: str
    origin: str
    subject: str
    current_version_id: str
    versions: list[Version]
    connections: list[Connection]
    operations: list[Operation]
    evidence: list[Evidence]


class InteractionDetail(BaseModel):
    id: str
    project_id: str
    status: str
    note_ids: list[str] = Field(default_factory=list)
    operations: list[Operation]
    evidence: list[Evidence]


def decode_operation(row):
    return Operation.model_validate(
        {
            **dict(row),
            "target_note_ids": json.loads(row["target_note_ids"]),
            "input_event_ids": json.loads(row["input_event_ids"]),
        }
    )


def inspect_interaction(store, project_id, interaction_id):
    with store.connection() as db:
        sources = db.execute(
            """SELECT s.* FROM interaction_events i JOIN source_events s ON s.id=i.source_id
               WHERE i.interaction_id=? AND s.project_id=? ORDER BY i.position""",
            (interaction_id, project_id),
        ).fetchall()
        if not sources:
            return None
        completed = db.execute(
            "SELECT * FROM completed_interactions WHERE id=?", (interaction_id,)
        ).fetchone()
        operations = db.execute(
            """SELECT * FROM memory_operations WHERE project_id=? AND interaction_id=?
               ORDER BY rowid""",
            (project_id, interaction_id),
        ).fetchall()
    return InteractionDetail(
        id=interaction_id,
        project_id=project_id,
        status="completed" if completed else "pending",
        note_ids=json.loads(completed["note_ids"]) if completed else [],
        operations=[decode_operation(row) for row in operations],
        evidence=[Evidence.model_validate(dict(row)) for row in sources],
    )


def inspect_note(store, project_id, note_id):
    raw = store.inspect(project_id, note_id)
    if raw is None:
        return None
    connections = []
    evidence_ids = set()
    with store.connection() as db:
        for link in raw["connections"]:
            neighbor_version = (
                link["to_version"] if link["from_note_id"] == note_id else link["from_version"]
            )
            neighbor = db.execute(
                """SELECT v.*, n.current_version_id FROM memory_versions v
                   JOIN memory_notes n ON n.id=v.note_id WHERE v.id=? AND n.project_id=?""",
                (neighbor_version, project_id),
            ).fetchone()
            if neighbor is None:
                continue
            status = link["status"]
            if neighbor["status"] != "active" or neighbor_version != neighbor["current_version_id"]:
                status = "historical"
            connections.append(
                Connection.model_validate(
                    {
                        **link,
                        "status": status,
                        "neighbor_id": neighbor["note_id"],
                        "neighbor_text": neighbor["text"],
                        "neighbor_version_id": neighbor_version,
                        "neighbor_status": neighbor["status"],
                    }
                )
            )
            evidence_ids.update(link["source_ids"])
    for version in raw["versions"]:
        evidence_ids.update(source["id"] for source in version["sources"])
        for revision in version["metadata_history"]:
            evidence_ids.update(revision["source_ids"])
    for operation in raw["operations"]:
        evidence_ids.update(operation["input_event_ids"])
    return NoteDetail.model_validate(
        {
            **raw,
            "connections": connections,
            "evidence": store.sources(project_id, sorted(evidence_ids)),
        }
    )
