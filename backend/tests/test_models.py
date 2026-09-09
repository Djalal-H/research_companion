import json

import httpx
import pytest

from app import agent, models
from app.config import Settings
from app.memory.schemas import Candidate


def test_seekai_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "openai:qwen3.8-flash")
    monkeypatch.setenv("RESEARCH_MODEL_BASE_URL", "https://seekai.cc/v1")
    monkeypatch.setenv("RESEARCH_MODEL_API_KEY", "test-provider-key")
    settings = Settings.from_env()
    assert settings.model == "openai:qwen3.8-flash"
    assert settings.model_base_url == "https://seekai.cc/v1"
    assert settings.model_api_key.get_secret_value() == "test-provider-key"
    assert "test-provider-key" not in repr(settings)
    assert "test-provider-key" not in settings.model_dump_json()


@pytest.mark.parametrize(
    ("model_name", "base_url"),
    [
        ("qwen3.8-flash", "https://seekai.cc/v1"),
        ("nvidia/nemotron-3.5-lightning:free", "https://openrouter.ai/api/v1"),
    ],
)
def test_custom_provider_chat_tools_streaming_and_memory(monkeypatch, model_name, base_url):
    requests = []

    def respond(request):
        assert str(request.url) == f"{base_url}/chat/completions"
        assert request.headers["authorization"] == "Bearer test-provider-key"
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == model_name
        assert "response_format" not in payload
        if payload.get("stream"):
            chunks = [
                {
                    "id": "stream",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "Ready"},
                            "finish_reason": None,
                        },
                    ],
                },
                {
                    "id": "stream",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": model_name,
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": "stop"},
                    ],
                },
            ]
            content = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
            return httpx.Response(
                200,
                text=content + "data: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        name = payload["tools"][0]["function"]["name"]
        arguments = {
            "lookup": {"query": "memory"},
            "Extraction": {"candidates": [], "summary": {"text": "", "source_ids": []}},
            "Decision": {"action": "ADD", "target_note_id": None, "reason": "New finding"},
            "Enrichment": {
                "metadata": {"context": "User finding", "keywords": [], "tags": []},
                "links": [],
                "evolutions": [],
            },
        }[name]
        return httpx.Response(
            200,
            json={
                "id": "completion",
                "object": "chat.completion",
                "created": 1,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call",
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(arguments),
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    original_init = models.init_chat_model
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:

        def initialize(model, **kwargs):
            return original_init(model, http_client=client, **kwargs)

        monkeypatch.setattr(models, "init_chat_model", initialize)
        settings = Settings(
            model=f"openai:{model_name}",
            model_base_url=base_url,
            model_api_key="test-provider-key",
        )
        chat = models.build_chat_model(settings)

        def lookup(query: str) -> str:
            """Find a memory."""
            return query

        response = chat.bind_tools([lookup]).invoke("Find memory")
        assert response.tool_calls[0]["args"] == {"query": "memory"}
        assert "".join(chunk.text for chunk in chat.stream("Hello")) == "Ready"
        policy = models.build_memory_policy(settings)
        assert policy.extract({"current": []}).candidates == []
        decision = policy.reconcile(
            Candidate(
                text="A finding",
                kind="finding",
                subject="research",
                origin="user",
                source_ids=["source"],
            ),
            [],
            {},
        )
        assert decision.action == "ADD"
        assert policy.enrich({"note": {}, "neighbors": [], "sources": []}).metadata.context == (
            "User finding"
        )
    assert len(requests) == 5
    assert requests[2]["tool_choice"]["function"]["name"] == "Extraction"
    assert requests[3]["tool_choice"]["function"]["name"] == "Decision"


def test_custom_endpoint_cannot_be_silently_ignored():
    with pytest.raises(ValueError, match="requires an openai:"):
        models.build_chat_model(Settings(model_base_url="https://seekai.cc/v1"))


def test_graph_accepts_openrouter_suffix_and_disables_delegation(settings):
    configured = Settings(
        model="openai:nvidia/nemotron-3.5-lightning:free",
        model_base_url="https://openrouter.ai/api/v1",
        model_api_key="test-provider-key",
        db_path=settings.db_path,
        papers_dir=settings.papers_dir,
    )
    graph = agent.build_graph(configured)
    tools = graph.nodes["tools"].bound.tools_by_name
    assert "write_todos" in tools
    assert "recall_memories" in tools
    assert "task" not in tools
