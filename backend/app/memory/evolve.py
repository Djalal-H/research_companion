"""Bounded, nonrecursive enrichment prepared before the SQLite write transaction."""

import json

from app.memory.prompts import ENRICH, INPUT_BUDGET
from app.memory.schemas import Enrichment
from app.memory.search import cosine


def searchable(note, metadata):
    return "\n".join([note["text"], metadata["context"], *metadata["keywords"], *metadata["tags"]])


def prepare(store, policy, notes, changes, evidence):
    accepted = {note_id for _, decision, note_id in changes if decision.action != "NOOP"}
    if not accepted:
        return {"metadata": {}, "links": []}
    by_id = {note["id"]: note for note in notes}
    vectors = {key: store.embedding_for(note) for key, note in by_id.items()}
    updates, links, evolved = {}, [], set()
    for note_id in sorted(accepted):
        note = by_id[note_id]
        ranked = sorted(
            (other for other in notes if other["id"] != note_id),
            key=lambda other: (-cosine(vectors[note_id], vectors[other["id"]]), other["id"]),
        )[:5]
        context = {"note": compact(note), "neighbors": [], "sources": []}
        for other in ranked:
            payload = compact(other)
            trial = {**context, "neighbors": [*context["neighbors"], payload]}
            if len(json.dumps(trial)) + len(ENRICH) < INPUT_BUDGET - 6000:
                context["neighbors"].append(payload)
        visible = {n["id"]: n for n in context["neighbors"]}
        ids = set(note["source_ids"])
        for other in visible.values():
            ids.update(other["source_ids"])
        for source_id in sorted(ids):
            source = evidence.get(source_id)
            if source:
                entry = {
                    "id": source_id,
                    "role": source["role"],
                    "content": source["content"][:600],
                }
                trial = {**context, "sources": [*context["sources"], entry]}
                if len(json.dumps(trial, ensure_ascii=False)) + len(ENRICH) <= INPUT_BUDGET:
                    context["sources"].append(entry)
        result = Enrichment.model_validate(policy.enrich(context))
        visible_sources = {source["id"] for source in context["sources"]}
        for proposal in [*result.links, *result.evolutions]:
            target = visible.get(proposal.target_note_id)
            refs = set(proposal.source_ids)
            if (
                target is None
                or not refs.issubset(visible_sources)
                or not refs.issubset(set(note["source_ids"]) | set(target["source_ids"]))
                or not refs.intersection(note["source_ids"])
                or not refs.intersection(target["source_ids"])
            ):
                raise ValueError("Link/evolution requires visible evidence from both endpoints")
        updates[note_id] = payload_for(
            store,
            note,
            result.metadata.model_dump(),
            note["source_ids"],
            "Constructed note metadata",
        )
        for proposal in result.links:
            links.append({"from": note_id, **proposal.model_dump()})
        seen = set()
        for proposal in result.evolutions:
            target_id = proposal.target_note_id
            if target_id in seen:
                raise ValueError("A target may evolve only once per enrichment")
            seen.add(target_id)
            # Newly accepted notes get their own enrichment. Older notes evolve once per write.
            if target_id in accepted or target_id in evolved:
                continue
            target = by_id[target_id]
            if note["evidence_order"] < max(
                target["evidence_order"], target.get("metadata_order", 0)
            ):
                continue
            evolved.add(target_id)
            updates[target_id] = payload_for(
                store,
                target,
                proposal.metadata.model_dump(),
                proposal.source_ids,
                proposal.reason,
            )
    return {"metadata": updates, "links": links}


def compact(note):
    return {
        key: note[key][:20] if key == "source_ids" else note[key]
        for key in ("id", "text", "kind", "origin", "subject", "source_ids", "metadata")
        if key in note
    }


def payload_for(store, note, metadata, source_ids, reason):
    return {
        "metadata": metadata,
        "embedding": store.embeddings.embed(searchable(note, metadata)),
        "source_ids": source_ids,
        "reason": reason,
    }
