"""List or retry recorded interactions without rerunning the research agent."""

import argparse
import json

from app.config import Settings
from app.memory.embeddings import build_embeddings
from app.memory.reconcile import MemoryEngine
from app.memory.store import MemoryStore
from app.models import build_memory_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interaction-id")
    parser.add_argument("--thread-id")
    args = parser.parse_args()
    if bool(args.interaction_id) != bool(args.thread_id):
        parser.error(
            "Supply both --interaction-id and --thread-id, or neither to list pending work"
        )
    settings = Settings.from_env()
    store = MemoryStore(settings.db_path, embeddings=build_embeddings(settings))
    if not args.interaction_id:
        with store.connection() as db:
            pending = db.execute(
                """SELECT evidence.interaction_id, source.thread_id, source.recorded_at
                   FROM interaction_events evidence JOIN source_events source
                   ON source.id=evidence.source_id WHERE evidence.position=0
                   AND source.project_id=? AND NOT EXISTS
                     (SELECT 1 FROM completed_interactions done
                      WHERE done.id=evidence.interaction_id)
                   ORDER BY source.rowid""",
                (settings.project_id,),
            ).fetchall()
        print(json.dumps([dict(row) for row in pending], indent=2))
        return
    policy = build_memory_policy(settings)
    affected = MemoryEngine(store, policy).retry(
        settings.project_id,
        args.thread_id,
        args.interaction_id,
    )
    print(json.dumps({"memory_changes": affected, "memory_status": "ready"}))


if __name__ == "__main__":
    main()
