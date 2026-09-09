from pathlib import Path

from pydantic import BaseModel, Field

from app.memory.search import cosine, vector


class Section(BaseModel):
    id: str
    title: str
    text: str = Field(min_length=1)


class Paper(BaseModel):
    id: str
    title: str
    url: str
    sections: list[Section] = Field(min_length=1)


class PaperCorpus:
    def __init__(self, directory: Path):
        self.papers = {}
        for path in sorted(directory.glob("*.json")):
            if path.name == "manifest.json":
                continue
            paper = Paper.model_validate_json(path.read_text())
            if paper.id in self.papers:
                raise ValueError(f"Duplicate paper ID: {paper.id}")
            self.papers[paper.id] = paper
        if not self.papers:
            raise ValueError("No prepared papers. Run: uv run python scripts/prepare_papers.py")

    def search(self, query: str) -> list[dict]:
        q = vector(query)
        matches = []
        for paper in self.papers.values():
            for section in paper.sections:
                score = cosine(q, vector(f"{paper.title} {section.title} {section.text}"))
                if score > 0:
                    matches.append(
                        {
                            "paper_id": paper.id,
                            "title": paper.title,
                            "section": section.title,
                            "source_id": f"paper:{paper.id}:{section.id}",
                            "url": f"{paper.url}#{section.id}",
                            "excerpt": section.text[:500],
                            "score": round(score, 6),
                        }
                    )
        return sorted(matches, key=lambda m: (-m["score"], m["source_id"]))[:10]

    def read(self, paper_id: str) -> dict:
        # Lookup by ID; never interpret model arguments as a filesystem path.
        paper = self.papers.get(paper_id)
        if paper is None:
            return {"error": "Unknown paper ID", "available_ids": sorted(self.papers)}
        data = paper.model_dump()
        for section in data["sections"]:
            section["source_id"] = f"paper:{paper.id}:{section['id']}"
            section["url"] = f"{paper.url}#{section['id']}"
        return data
