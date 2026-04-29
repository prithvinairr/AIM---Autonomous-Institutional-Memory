"""Abstract base for entity/relationship extractors."""
from __future__ import annotations

from abc import ABC, abstractmethod

from aim.extraction.schemas import ExtractionResult


class Extractor(ABC):
    """Provider-agnostic extraction interface.

    Concrete implementations (LLM-based, rule-based, hybrid) all satisfy
    this contract so the ingest pipeline and webhook handlers are decoupled
    from any specific extraction strategy.
    """

    @abstractmethod
    async def extract(
        self,
        text: str,
        *,
        source_uri: str = "",
        entity_types: list[str] | None = None,
    ) -> ExtractionResult:
        """Extract entities and relationships from raw text.

        Parameters
        ----------
        text:
            Raw text content (Slack message, Jira description, document body).
        source_uri:
            Origin URI for provenance tracking.
        entity_types:
            Restrict extraction to these entity types.  ``None`` = all known types.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the extractor backend is reachable."""
        ...
