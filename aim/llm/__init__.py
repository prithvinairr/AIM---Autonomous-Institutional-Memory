"""Pluggable LLM and Embedding provider abstraction.

Supports Anthropic, OpenAI, and any OpenAI-compatible local endpoint
(Ollama, vLLM, llama.cpp server) via configuration — no code changes
required to switch providers.
"""
from aim.llm.base import EmbeddingProvider, LLMProvider
from aim.llm.factory import get_embedding_provider, get_llm_provider

__all__ = [
    "LLMProvider",
    "EmbeddingProvider",
    "get_llm_provider",
    "get_embedding_provider",
]
