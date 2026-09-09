from pathlib import Path

from pydantic import BaseModel, Field, SecretStr

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    model: str = "google_genai:gemini-3.5-flash"
    model_base_url: str | None = None
    model_api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    embedding_model: str = "google_genai:gemini-embedding-001"
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    project_id: str = Field(default="research-demo", min_length=1)
    db_path: Path = ROOT / "data/runtime/memory.sqlite3"
    papers_dir: Path = ROOT / "data/papers"
    memory_budget: int = Field(default=2000, ge=64, le=10000)

    @classmethod
    def from_env(cls):
        import os

        from dotenv import load_dotenv

        load_dotenv(ROOT / "backend/.env")
        names = {
            "embedding_model": "RESEARCH_EMBEDDING_MODEL",
            "embedding_base_url": "RESEARCH_EMBEDDING_BASE_URL",
            "embedding_api_key": "RESEARCH_EMBEDDING_API_KEY",
            "model": "RESEARCH_MODEL",
            "model_base_url": "RESEARCH_MODEL_BASE_URL",
            "model_api_key": "RESEARCH_MODEL_API_KEY",
            "project_id": "RESEARCH_PROJECT_ID",
            "db_path": "RESEARCH_DB_PATH",
            "papers_dir": "RESEARCH_PAPERS_DIR",
            "memory_budget": "RESEARCH_MEMORY_BUDGET",
        }
        return cls(**{field: os.environ[key] for field, key in names.items() if key in os.environ})
