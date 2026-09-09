"""Read-only inspection routes mounted alongside the LangGraph server."""

import asyncio

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.config import Settings
from app.memory.inspection import inspect_interaction, inspect_note
from app.memory.store import MemoryStore


def create_app(settings=None):
    # Resolve configuration lazily so importing the ASGI app needs no provider credentials.
    def read(kind, identifier):
        configured = settings or Settings.from_env()
        store = MemoryStore(configured.db_path)
        inspect = inspect_note if kind == "note" else inspect_interaction
        return inspect(store, configured.project_id, identifier)

    async def note(request):
        result = await asyncio.to_thread(read, "note", request.path_params["note_id"])
        return respond(result)

    async def interaction(request):
        result = await asyncio.to_thread(read, "interaction", request.path_params["interaction_id"])
        return respond(result)

    return Starlette(
        routes=[
            Route("/memory/notes/{note_id}", note, methods=["GET"]),
            Route("/memory/interactions/{interaction_id}", interaction, methods=["GET"]),
        ]
    )


def respond(result):
    if result is None:
        return JSONResponse({"error": "Memory record not found"}, status_code=404)
    return JSONResponse(result.model_dump(), headers={"Cache-Control": "no-store"})


app = create_app()
