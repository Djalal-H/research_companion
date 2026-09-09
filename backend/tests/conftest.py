import json

import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    for paper_id in ["amem", "mem0", "longmemeval"]:
        (papers / f"{paper_id}.json").write_text(
            json.dumps(
                {
                    "id": paper_id,
                    "title": f"{paper_id} memory research",
                    "url": f"https://example.org/{paper_id}",
                    "sections": [
                        {
                            "id": "S2",
                            "title": "Methods",
                            "text": "Synthetic fixture for testing paper retrieval.",
                        }
                    ],
                }
            )
        )
    return Settings(model="demo", db_path=tmp_path / "memory.sqlite3", papers_dir=papers)
