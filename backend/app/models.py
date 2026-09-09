from langchain.chat_models import init_chat_model

from app.config import Settings
from app.memory.extract import ModelPolicy, ScriptedPolicy


def build_chat_model(settings: Settings):
    if settings.model == "demo":
        from app.demo_model import DemoModel

        return DemoModel()
    options = {"timeout": 60, "max_retries": 1}
    if settings.model_base_url:
        if not settings.model.startswith("openai:"):
            raise ValueError("RESEARCH_MODEL_BASE_URL requires an openai: model identifier")
        options["base_url"] = settings.model_base_url
    if settings.model_api_key:
        options["api_key"] = settings.model_api_key.get_secret_value()
    if settings.model.startswith("openai:"):
        options.update(use_responses_api=False, stream_usage=False)
    return init_chat_model(settings.model, **options)


def build_memory_policy(settings: Settings):
    if settings.model == "demo":
        return ScriptedPolicy()
    return ModelPolicy(
        build_chat_model(settings),
        settings.model,
        structured_output_method="function_calling"
        if settings.model.startswith("openai:")
        else None,
    )
