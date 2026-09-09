import json
import re
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.constants import TAG_NOSTREAM

from app.memory.prompts import ENRICH, EXTRACT, INPUT_BUDGET, PROMPT_VERSION, RECONCILE
from app.memory.schemas import (
    Candidate,
    Decision,
    Enrichment,
    Evolution,
    Extraction,
    LinkProposal,
    Metadata,
    Summary,
)


class MemoryPolicy(Protocol):
    model_version: str
    prompt_version: str

    def enrich(self, context: dict) -> Enrichment: ...

    def extract(self, context: dict) -> Extraction: ...

    def reconcile(self, candidate: Candidate, neighbors: list[dict], context: dict) -> Decision: ...


class ModelPolicy:
    prompt_version = PROMPT_VERSION

    def __init__(self, model, model_version: str, *, structured_output_method: str | None = None):
        self.model_version = model_version
        options = {"method": structured_output_method} if structured_output_method else {}
        self.extractor = model.with_structured_output(Extraction, **options)
        self.reconciler = model.with_structured_output(Decision, **options)
        self.enricher = model.with_structured_output(Enrichment, **options)

    def _invoke(self, runnable, prompt, payload, schema):
        serialized = json.dumps(payload, ensure_ascii=False)
        if len(prompt) + len(serialized) > INPUT_BUDGET:
            raise ValueError("Memory model input exceeds its bounded budget")
        result = runnable.invoke(
            [SystemMessage(content=prompt), HumanMessage(content=serialized)],
            config={"tags": [TAG_NOSTREAM, "memory-consolidation"]},
        )
        return schema.model_validate(result)

    def enrich(self, context: dict) -> Enrichment:
        return self._invoke(self.enricher, ENRICH, context, Enrichment)

    def extract(self, context: dict) -> Extraction:
        return self._invoke(self.extractor, EXTRACT, context, Extraction)

    def reconcile(self, candidate: Candidate, neighbors: list[dict], context: dict) -> Decision:
        return self._invoke(
            self.reconciler,
            RECONCILE,
            {"candidate": candidate.model_dump(), "neighbors": neighbors, "evidence": context},
            Decision,
        )


class ScriptedPolicy:
    """Explicit credential-free demo adapter; not a general language understanding model."""

    model_version = "demo:scripted-memory"
    prompt_version = PROMPT_VERSION

    def enrich(self, context: dict) -> Enrichment:
        note = context["note"]
        result = Enrichment(
            metadata=Metadata(
                context=f"{note['origin']} {note['kind']} about {note['subject']}",
                keywords=list(dict.fromkeys(re.findall(r"\w+", note["subject"])))[:8],
                tags=[note["kind"], note["origin"]],
            )
        )

        # Demo-only relationships: observed method findings inform the user's objective.
        if note["subject"] == "research objective":
            result.metadata.keywords = ["research", "objective", "project", "experiment"]
            visible = {source["id"] for source in context["sources"]}
            for neighbor in context["neighbors"]:
                if neighbor["origin"] != "paper" and neighbor["subject"] != "time budget":
                    continue
                refs = list(dict.fromkeys(note["source_ids"][:1] + neighbor["source_ids"][:1]))
                if not set(refs).issubset(visible):
                    continue
                reason = (
                    "Observed paper method is relevant to the stated research objective"
                    if neighbor["origin"] == "paper"
                    else "The stated time budget constrains the research objective"
                )
                result.links.append(
                    LinkProposal(
                        target_note_id=neighbor["id"],
                        relation="related_to",
                        source_ids=refs,
                        reason=reason,
                    )
                )
                result.evolutions.append(
                    Evolution(
                        target_note_id=neighbor["id"],
                        source_ids=refs,
                        reason=reason,
                        metadata=Metadata(
                            context=f"Research method considered for objective: {note['text']}"[
                                :600
                            ],
                            keywords=["research", "memory", "experiment"],
                            tags=[neighbor["kind"], neighbor["origin"], "project relevance"],
                        ),
                    )
                )
        return result

    def extract(self, context: dict) -> Extraction:
        candidates = []
        for event in context["current"]:
            if event["role"] != "human" or not event["content"].strip():
                continue
            for sentence in re.split(r"(?<=[.!?])\s+", event["content"]):
                lowered = sentence.lower()
                if lowered.startswith(("design ", "compare ", "read ", "write ")):
                    continue
                kind, subject = "finding", "user statement"
                if re.search(r"\b(week|weeks|day|days|budget)\b", lowered):
                    kind, subject = "constraint", "time budget"
                elif re.search(r"\b(focus|interested|objective)\b", lowered):
                    kind, subject = "preference", "research objective"
                elif lowered.endswith("?"):
                    kind, subject = "question", "research question"
                candidates.append(
                    Candidate(
                        text=sentence[:2000],
                        kind=kind,
                        subject=subject,
                        origin="user",
                        source_ids=[event["id"]],
                    )
                )
        # Search results are bounded excerpts. Decode only complete observed objects,
        # including when the extraction budget truncates the tail of the JSON array.
        for event in context["current"]:
            if event["role"] != "tool" or event.get("tool_name") != "search_papers":
                continue
            remaining = event["content"].lstrip()
            if not remaining.startswith("[") or not event.get("source_location"):
                continue
            remaining = remaining[1:].lstrip()
            while remaining:
                try:
                    hit, end = json.JSONDecoder().raw_decode(remaining)
                except ValueError:
                    break
                if (
                    isinstance(hit, dict)
                    and hit.get("source_id")
                    in {
                        "paper:amem:S3",
                        "paper:mem0:S2",
                    }
                    and hit.get("excerpt")
                ):
                    candidates.append(
                        Candidate(
                            text=hit["excerpt"][:500],
                            kind="finding",
                            origin="paper",
                            subject=f"research method {hit['source_id']}",
                            source_ids=[event["id"]],
                        )
                    )
                remaining = remaining[end:].lstrip()
                if not remaining.startswith(","):
                    break
                remaining = remaining[1:].lstrip()
        evidence = context["recent"] + context["current"]
        human = [event for event in evidence if event["role"] == "human"]
        return Extraction(
            candidates=candidates[:20],
            summary=Summary(
                text="\n".join(event["content"] for event in human)[-2000:],
                source_ids=[event["id"] for event in human][-40:],
            ),
        )

    def reconcile(self, candidate: Candidate, neighbors: list[dict], context: dict) -> Decision:
        compatible = [
            note
            for note in neighbors
            if all(note[key] == getattr(candidate, key) for key in ("kind", "subject", "origin"))
        ]

        def normalize(text):
            return " ".join(re.findall(r"\w+", text.lower()))

        for note in compatible:
            if normalize(note["text"]) == normalize(candidate.text):
                return Decision(action="NOOP", target_note_id=note["id"], reason="Repeated fact")
        if len(compatible) == 1:
            lowered = candidate.text.lower().replace("’", "'")
            if any(word in lowered for word in ("correction", "was wrong", "meant ")):
                return Decision(
                    action="UPDATE",
                    target_note_id=compatible[0]["id"],
                    reason="Explicit correction in scripted demo evidence",
                )
            if any(word in lowered for word in ("now ", "instead", "let's focus", "only have")):
                return Decision(
                    action="SUPERSEDE",
                    target_note_id=compatible[0]["id"],
                    reason="Explicit change in scripted demo evidence",
                )
        return Decision(action="ADD", reason="New fact; retain any unresolved conflicting evidence")
