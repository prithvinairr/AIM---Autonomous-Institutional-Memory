"""LLM-based entity extraction pipeline.

Extracts Person, Service, Incident, Decision (and more) entities plus
their relationships from raw Slack / Jira / Confluence text, deduplicates
against the existing graph, and feeds into the ingest worker.
"""
from aim.extraction.base import Extractor
from aim.extraction.deduplicator import Deduplicator, get_deduplicator
from aim.extraction.llm_extractor import LLMExtractor, get_extractor
from aim.extraction.schemas import (
    ENTITY_TYPES,
    RELATIONSHIP_TYPES,
    ExtractionBatch,
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelationship,
)

__all__ = [
    "Extractor",
    "Deduplicator",
    "get_deduplicator",
    "LLMExtractor",
    "get_extractor",
    "ENTITY_TYPES",
    "RELATIONSHIP_TYPES",
    "ExtractionBatch",
    "ExtractionResult",
    "ExtractedEntity",
    "ExtractedRelationship",
]
