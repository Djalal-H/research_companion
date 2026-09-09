"""Versioned embedding spaces; the lexical adapter is only for offline demos/tests."""

import math

from app.memory.search import vector


class Embeddings:
    def __init__(self, model="demo:lexical", *, base_url=None, api_key=None):
        self.model = model
        self.space = model + ("@" + base_url if base_url else "")
        self.base_url = base_url
        self.api_key = api_key
        self._client = None

    def embed(self, text, *, query=False):
        if self.model == "demo:lexical":
            return vector(text)
        if self._client is None:
            provider, _, name = self.model.partition(":")
            options = {"model": name}
            if self.api_key:
                options["api_key"] = self.api_key.get_secret_value()
            if provider == "openai":
                from langchain_openai import OpenAIEmbeddings

                options.update(max_retries=1, request_timeout=60)
                if self.base_url:
                    options.update(base_url=self.base_url, check_embedding_ctx_length=False)
                self._client = OpenAIEmbeddings(**options)
            elif provider == "google_genai" and not self.base_url:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings

                self._client = GoogleGenerativeAIEmbeddings(**options)
            else:
                raise ValueError("Embedding model requires openai: or google_genai: provider")
        values = (
            self._client.embed_query(text) if query else self._client.embed_documents([text])[0]
        )
        if not values or any(not math.isfinite(value) for value in values):
            raise ValueError("Embedding must be nonempty and finite")
        norm = math.sqrt(sum(value * value for value in values))
        if not norm or not math.isfinite(norm):
            raise ValueError("Embedding must have nonzero norm")
        return {str(index): value / norm for index, value in enumerate(values)}


def build_embeddings(settings):
    return Embeddings(
        "demo:lexical" if settings.model == "demo" else settings.embedding_model,
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
    )
