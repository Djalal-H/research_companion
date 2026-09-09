import json

from app.memory.evolve import prepare
from app.memory.extract import MemoryPolicy
from app.memory.prompts import EXTRACT, INPUT_BUDGET, RECONCILE
from app.memory.schemas import Candidate, Decision, Extraction
from app.memory.search import cosine, vector
from app.memory.store import ConcurrentWriteError, MemoryStore, stable_id


def serialized_size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False))


def excerpt(event: dict, limit: int = 4000) -> dict:
    return {
        "id": event["id"],
        "role": event["role"],
        "content": event["content"][:limit],
        "truncated": len(event["content"]) > limit,
        "tool_name": event.get("tool_name"),
        "source_location": event.get("source_location"),
        "recorded_at": event.get("recorded_at"),
    }


def extraction_context(snapshot: dict, sources: list[dict]) -> dict:
    context = {"summary": snapshot["summary"], "recent": [], "current": []}
    ordered = [sources[0], sources[-1], *sources[1:-1]]
    for event in ordered:
        compact = excerpt(event)
        context["current"].append(compact)
        if serialized_size(context) + len(EXTRACT) > INPUT_BUDGET:
            context["current"].pop()
    order = {event["id"]: position for position, event in enumerate(sources)}
    context["current"].sort(key=lambda event: order[event["id"]])
    for event in reversed(snapshot["recent"]):
        context["recent"].insert(0, excerpt(event, 1000))
        if serialized_size(context) + len(EXTRACT) > INPUT_BUDGET:
            context["recent"].pop(0)
            break
    return context


def validate_extraction(extraction: Extraction, context: dict, evidence: dict):
    visible_ids = {event["id"] for event in context["current"] + context["recent"]}
    visible_ids.update(context["summary"]["source_ids"])
    current_ids = {event["id"] for event in context["current"]}
    referenced = set(extraction.summary.source_ids)
    if extraction.summary.text and not referenced:
        raise ValueError("A summary requires source evidence")
    for candidate in extraction.candidates:
        referenced.update(candidate.source_ids)
        if not current_ids.intersection(candidate.source_ids):
            raise ValueError("Each candidate requires evidence from the current exchange")
    if not referenced.issubset(visible_ids) or not referenced.issubset(evidence):
        raise ValueError("Unknown or out-of-scope source reference")
    for candidate in extraction.candidates:
        supporting = [evidence[source_id] for source_id in candidate.source_ids]
        role = {"user": "human", "assistant": "ai", "paper": "tool"}[candidate.origin]
        if not any(source["role"] == role and source["id"] in current_ids for source in supporting):
            raise ValueError("Candidate origin does not match its source evidence")
        if candidate.origin == "paper" and not any(
            source["role"] == "tool"
            and source.get("tool_name") in {"read_paper", "search_papers"}
            and source.get("source_location")
            for source in supporting
        ):
            raise ValueError("Paper findings require observed paper tool evidence")


def neighborhood(candidate: Candidate, notes: list[dict], store=None) -> list[dict]:
    query = store.embeddings.embed(candidate.text, query=True) if store else vector(candidate.text)
    vectors = {
        note["id"]: store.embedding_for(note) if store else json.loads(note["search_vector"])
        for note in notes
    }
    ranked = sorted(
        notes,
        key=lambda note: (-cosine(query, vectors[note["id"]]), note["id"]),
    )
    similar = [note for note in ranked if cosine(query, vectors[note["id"]]) > 0][:10]
    exact = [note for note in ranked if note["subject"] == candidate.subject][:10]
    return list({note["id"]: note for note in [*exact, *similar]}.values())


def decision_context(candidate, neighbors, evidence):
    context = {"sources": []}
    for source_id in candidate.source_ids:
        source = excerpt(evidence[source_id], 2000)
        if serialized_size(context) + serialized_size(source) <= 6000:
            context["sources"].append(source)
    selected = []
    for note in neighbors:
        compact = {key: note[key] for key in ("id", "kind", "origin", "subject", "text")}
        payload = {
            "candidate": candidate.model_dump(),
            "neighbors": [*selected, compact],
            "evidence": context,
        }
        if serialized_size(payload) + len(RECONCILE) <= INPUT_BUDGET:
            selected.append(compact)
    return selected, context


class MemoryEngine:
    def __init__(self, store: MemoryStore, policy: MemoryPolicy):
        self.store = store
        self.policy = policy

    def ingest(self, project_id: str, thread_id: str, events: list[dict]) -> list[str]:
        interaction_id, sources = self.store.record(project_id, thread_id, events)
        return self._consolidate(project_id, thread_id, interaction_id, sources)

    def _consolidate(self, project_id, thread_id, interaction_id, sources):
        done = self.store.completed(interaction_id)
        if done is not None:
            return done
        try:
            for _attempt in range(3):
                snapshot = self.store.snapshot(project_id, thread_id, interaction_id)
                context = extraction_context(snapshot, sources)
                source_ids = [event["id"] for event in context["current"] + context["recent"]]
                source_ids.extend(context["summary"]["source_ids"])
                evidence = {
                    event["id"]: event for event in self.store.sources(project_id, source_ids)
                }
                extraction = Extraction.model_validate(self.policy.extract(context))
                validate_extraction(extraction, context, evidence)
                notes = snapshot["notes"]
                for note in notes:
                    evidence.update(
                        {
                            event["id"]: event
                            for event in self.store.sources(project_id, note["source_ids"])
                        }
                    )
                changes = []
                for position, candidate in enumerate(extraction.candidates):
                    neighbors, observed = decision_context(
                        candidate,
                        neighborhood(candidate, notes, self.store),
                        evidence,
                    )
                    duplicate = next(
                        (
                            note
                            for note in notes
                            if all(
                                note[key] == getattr(candidate, key)
                                for key in ("text", "kind", "subject", "origin")
                            )
                        ),
                        None,
                    )
                    if duplicate:
                        decision = Decision(
                            action="NOOP",
                            target_note_id=duplicate["id"],
                            reason="Exact repeated fact",
                        )
                    else:
                        decision = Decision.model_validate(
                            self.policy.reconcile(candidate, neighbors, observed),
                        )
                    targets = {note["id"]: note for note in neighbors}
                    if duplicate:
                        targets[duplicate["id"]] = duplicate
                    if decision.target_note_id:
                        target = targets.get(decision.target_note_id)
                        if target is None or any(
                            target[key] != getattr(candidate, key)
                            for key in ("kind", "origin", "subject")
                        ):
                            raise ValueError("Invalid or incompatible reconciliation target")
                    evidence_order = max(
                        evidence[source_id]["event_order"] for source_id in candidate.source_ids
                    )
                    if decision.action in {"UPDATE", "SUPERSEDE"}:
                        original = next(
                            note for note in notes if note["id"] == decision.target_note_id
                        )
                        if evidence_order < original["evidence_order"]:
                            decision = Decision(
                                action="NOOP",
                                reason="Earlier evidence cannot invalidate the newer version of "
                                + original["id"],
                            )
                    note_id = decision.target_note_id
                    if decision.action == "ADD":
                        note_id = stable_id(project_id, interaction_id, str(position), "note")
                    changes.append((candidate, decision, note_id))
                    if decision.action != "NOOP":
                        notes = [note for note in notes if note["id"] != note_id]
                        notes.append(
                            {
                                "id": note_id,
                                **candidate.model_dump(),
                                "search_vector": json.dumps(vector(candidate.text)),
                                "evidence_order": evidence_order,
                            }
                        )
                graph_changes = prepare(self.store, self.policy, notes, changes, evidence)
                try:
                    return self.store.commit(
                        project_id,
                        thread_id,
                        interaction_id,
                        snapshot["revision"],
                        changes,
                        extraction.summary,
                        self.policy,
                        graph_changes,
                    )
                except ConcurrentWriteError:
                    done = self.store.completed(interaction_id)
                    if done is not None:
                        return done
            raise ConcurrentWriteError("Project remained busy after three reconciliation attempts")
        except Exception as error:
            self.store.record_failure(project_id, interaction_id, sources, self.policy, error)
            raise

    def retry(self, project_id: str, thread_id: str, interaction_id: str) -> list[str]:
        with self.store.connection() as db:
            rows = db.execute(
                """SELECT s.* FROM source_events s JOIN interaction_events evidence
                   ON evidence.source_id=s.id WHERE evidence.interaction_id=?
                   AND s.project_id=? AND s.thread_id=? ORDER BY evidence.position""",
                (interaction_id, project_id, thread_id),
            ).fetchall()
        if not rows:
            raise ValueError("Unknown interaction in this project and thread")
        return self._consolidate(project_id, thread_id, interaction_id, [dict(row) for row in rows])
