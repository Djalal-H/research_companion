from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Kind = Literal["finding", "preference", "constraint", "decision", "question", "proposal"]
Origin = Literal["user", "assistant", "paper"]
Action = Literal["ADD", "UPDATE", "SUPERSEDE", "NOOP"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Candidate(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    kind: Kind
    subject: str = Field(min_length=1, max_length=200)
    origin: Origin
    source_ids: list[str] = Field(min_length=1, max_length=20)
    event_time: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_authority(self):
        self.subject = " ".join(self.subject.lower().split())
        self.source_ids = list(dict.fromkeys(self.source_ids))
        if self.kind in {"preference", "constraint", "decision", "question"}:
            if self.origin != "user":
                raise ValueError("User memories require user evidence")
        if self.kind == "proposal" and self.origin != "assistant":
            raise ValueError("Proposals must remain assistant-authored")
        if self.origin == "assistant" and self.kind != "proposal":
            raise ValueError("Assistant suggestions cannot become factual findings")
        return self


class Summary(StrictModel):
    text: str = Field(max_length=2000)
    source_ids: list[str] = Field(default_factory=list, max_length=40)


class Extraction(StrictModel):
    candidates: list[Candidate] = Field(max_length=20)
    summary: Summary


class Decision(StrictModel):
    action: Action
    target_note_id: str | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_target(self):
        if self.action in {"UPDATE", "SUPERSEDE"} and not self.target_note_id:
            raise ValueError("Revisions require an existing target")
        if self.action == "ADD" and self.target_note_id:
            raise ValueError("ADD cannot target an existing note")
        return self


class Metadata(StrictModel):
    context: str = Field(max_length=600)
    keywords: list[str] = Field(max_length=8)
    tags: list[str] = Field(max_length=8)

    @model_validator(mode="after")
    def bounded_labels(self):
        if any(not label.strip() or len(label) > 60 for label in self.keywords + self.tags):
            raise ValueError("Metadata labels must contain 1–60 characters")
        return self


class LinkProposal(StrictModel):
    target_note_id: str
    relation: Literal["related_to", "explains"]
    source_ids: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=600)


class Evolution(StrictModel):
    target_note_id: str
    metadata: Metadata
    source_ids: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=600)


class Enrichment(StrictModel):
    metadata: Metadata
    links: list[LinkProposal] = Field(default_factory=list, max_length=5)
    evolutions: list[Evolution] = Field(default_factory=list, max_length=5)
