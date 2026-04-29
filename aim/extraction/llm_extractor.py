"""LLM-based entity and relationship extractor.

Sends raw text to the configured LLM provider with a structured
extraction prompt.  The LLM returns JSON that is parsed into
``ExtractionResult`` objects.

Falls back gracefully: if the LLM output is malformed or the call
fails, an empty ``ExtractionResult`` is returned (never raises).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import structlog

from aim.config import get_settings
from aim.extraction.base import Extractor
from aim.extraction.schemas import (
    ENTITY_TYPES,
    RELATIONSHIP_TYPES,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
)
from aim.llm import get_llm_provider

log = structlog.get_logger(__name__)

# ── Extraction system prompt ─────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an entity extraction engine for a corporate knowledge graph.
Your job: read the input text and extract structured entities and relationships.

## Entity types
{entity_types}

## Relationship types
{relationship_types}

## Output format
Return ONLY a JSON object with this exact schema (no markdown fences, no commentary):
{{
  "entities": [
    {{
      "entity_type": "Service",
      "name": "Auth Service",
      "properties": {{"language": "Go", "team": "Platform"}},
      "confidence": 0.95
    }}
  ],
  "relationships": [
    {{
      "source_name": "Auth Service",
      "target_name": "Platform Team",
      "rel_type": "MAINTAINS",
      "properties": {{}},
      "confidence": 0.90
    }}
  ]
}}

## Rules
1. Entity names must be specific and canonical (not pronouns or vague references).
2. Confidence ranges: 0.9-1.0 for explicitly stated facts, 0.7-0.89 for strongly implied, 0.5-0.69 for inferred.
3. Only use the entity types and relationship types listed above.
4. If the text contains no extractable entities, return {{"entities": [], "relationships": []}}.
5. Deduplicate within the same extraction — do not emit the same entity twice.
6. For each entity, extract all relevant properties mentioned in the text.
7. Return valid JSON only — no trailing commas, no comments.
"""

# Maximum text length sent to the LLM (chars). Longer texts are truncated.
_MAX_TEXT_LENGTH = 16_000

_RELATIONSHIP_TYPE_ALIASES = {
    "CAUSED": "CAUSED_BY",
    "DECIDED": "APPROVED_BY",
}

_INCIDENT_ID_RE = re.compile(r"\bINC-\d{4}-\d+\b")
_SERVICE_RE = re.compile(r"\b(?:in|for|of)\s+the\s+([A-Za-z][A-Za-z0-9 -]+?\s+service)\b", re.IGNORECASE)
_SERVICE_SYMPTOM_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9 -]*?\s+service)"
    r"(?:\s+([A-Za-z0-9 -]*?rate limiter))?\s+"
    r"(?:started\s+)?(?:returning|throwing|emitting)\s+([45]\d{2})s?\b",
    re.IGNORECASE,
)
_LEAD_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+"
    r"(?:is\s+)?leading\s+the\s+response\b"
)
_ON_IT_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+is\s+on\s+it\b")
_REPORTED_BY_RE = re.compile(
    r"\breported\s+by\s+(?:the\s+)?([A-Za-z][A-Za-z0-9 &/-]+?\s+team)\b",
    re.IGNORECASE,
)
_CAUSE_RE = re.compile(r"\bwas\s+(?:a|an)\s+([^.;]+?)(?:\s+this\b|\s+at\b|[.;]|$)", re.IGNORECASE)
_ROLLBACK_RE = re.compile(r"\brolled\s+back\s+to\s+([^.;]+?)(?:\s+at\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?))?(?:[.;]|$)", re.IGNORECASE)
_DEPLOY_TIME_RE = re.compile(
    r"\bafter\s+the\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\s+deploy\b",
    re.IGNORECASE,
)


class LLMExtractor(Extractor):
    """Extract entities and relationships using the configured LLM provider."""

    async def extract(
        self,
        text: str,
        *,
        source_uri: str = "",
        entity_types: list[str] | None = None,
    ) -> ExtractionResult:
        if not text or not text.strip():
            return ExtractionResult(source_uri=source_uri)

        settings = get_settings()
        llm = get_llm_provider()

        # Resolve entity types
        allowed_types = (
            set(entity_types) & ENTITY_TYPES if entity_types else ENTITY_TYPES
        )

        system_msg = _SYSTEM_PROMPT.format(
            entity_types=", ".join(sorted(allowed_types)),
            relationship_types=", ".join(sorted(RELATIONSHIP_TYPES)),
        )

        truncated = text[:_MAX_TEXT_LENGTH]
        text_hash = hashlib.sha256(truncated.encode()).hexdigest()

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": truncated},
        ]

        try:
            response = await llm.invoke(
                messages,
                temperature=0.05,  # near-deterministic for extraction
                max_tokens=settings.llm_max_tokens,
            )
            raw_json = _extract_json(response.content)
            if raw_json is None:
                log.warning(
                    "extraction.json_parse_failed",
                    source_uri=source_uri,
                    response_preview=response.content[:200],
                )
                return ExtractionResult(
                    source_text_hash=text_hash,
                    source_uri=source_uri,
                )

            parsed = _parse_extraction(
                raw_json,
                allowed_types=allowed_types,
                text_hash=text_hash,
                source_uri=source_uri,
            )
            return _augment_incident_message_extraction(
                parsed,
                text=truncated,
                source_uri=source_uri,
                allowed_types=allowed_types,
            )

        except Exception as exc:
            log.error(
                "extraction.llm_error",
                source_uri=source_uri,
                error=str(exc),
            )
            return ExtractionResult(
                source_text_hash=text_hash,
                source_uri=source_uri,
            )

    async def health_check(self) -> bool:
        try:
            llm = get_llm_provider()
            return await llm.health_check()
        except Exception:
            return False


# ── Singleton ────────────────────────────────────────────────────────────────

_extractor_instance: LLMExtractor | None = None


def get_extractor() -> LLMExtractor:
    """Return the singleton LLM extractor."""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = LLMExtractor()
    return _extractor_instance


def reset_extractor() -> None:
    """Reset singleton — for tests only."""
    global _extractor_instance
    _extractor_instance = None


# ── JSON parsing helpers ─────────────────────────────────────────────────────

# Matches a JSON object, possibly wrapped in markdown fences
_JSON_BLOCK_RE = re.compile(
    r"\{[\s\S]*\}",
    re.DOTALL,
)


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Extract the first valid JSON object from LLM output.

    Handles markdown-fenced blocks, leading/trailing text, and minor
    formatting issues.
    """
    # Try direct parse first
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # Try regex extraction — find the outermost JSON object
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _canonical_service_name(raw: str) -> str:
    return " ".join(part.capitalize() for part in raw.strip().split())


def _canonical_team_name(raw: str) -> str:
    words = raw.strip().split()
    canonical: list[str] = []
    for word in words:
        if word.isupper() or (len(word) <= 3 and word.lower() != "the"):
            canonical.append(word.upper())
        else:
            canonical.append(word.capitalize())
    return " ".join(canonical)


def _append_entity_once(
    result: ExtractionResult,
    entity_type: str,
    name: str,
    *,
    properties: dict[str, Any] | None = None,
    confidence: float = 0.9,
) -> None:
    norm = (entity_type, name.lower().strip())
    for ent in result.entities:
        if (ent.entity_type, ent.name.lower().strip()) == norm:
            ent.properties.update(properties or {})
            ent.confidence = max(ent.confidence, confidence)
            return
    result.entities.append(
        ExtractedEntity(
            entity_type=entity_type,
            name=name,
            properties=properties or {},
            confidence=confidence,
        )
    )


def _append_relationship_once(
    result: ExtractionResult,
    source_name: str,
    target_name: str,
    rel_type: str,
    *,
    properties: dict[str, Any] | None = None,
    confidence: float = 0.88,
) -> None:
    norm = (source_name.lower().strip(), target_name.lower().strip(), rel_type)
    for rel in result.relationships:
        if (rel.source_name.lower().strip(), rel.target_name.lower().strip(), rel.rel_type) == norm:
            rel.properties.update(properties or {})
            rel.confidence = max(rel.confidence, confidence)
            return
    result.relationships.append(
        ExtractedRelationship(
            source_name=source_name,
            target_name=target_name,
            rel_type=rel_type,
            properties=properties or {},
            confidence=confidence,
        )
    )


def _augment_incident_message_extraction(
    result: ExtractionResult,
    *,
    text: str,
    source_uri: str,
    allowed_types: set[str],
) -> ExtractionResult:
    """Deterministically preserve explicit operational Slack incident facts."""
    incident_ids = _INCIDENT_ID_RE.findall(text)
    if not incident_ids or "Incident" not in allowed_types:
        return result

    incident_id = incident_ids[0]
    incident_props: dict[str, Any] = {
        "incident_id": incident_id,
        "summary": text.strip(),
        "source_uri": source_uri,
    }

    cause_match = _CAUSE_RE.search(text)
    if cause_match:
        incident_props["cause_summary"] = cause_match.group(1).strip()

    symptom_match = _SERVICE_SYMPTOM_RE.search(text)
    if symptom_match:
        status_code = symptom_match.group(3).strip()
        incident_props["status_code"] = status_code
        deploy_match = _DEPLOY_TIME_RE.search(text)
        if deploy_match:
            incident_props["deploy_time"] = deploy_match.group(1).strip()
        if not incident_props.get("cause_summary"):
            service_phrase = _canonical_service_name(symptom_match.group(1))
            component = (symptom_match.group(2) or "").strip().lower()
            mechanism = f"{service_phrase} returning {status_code}s"
            if component:
                mechanism = f"{service_phrase} {component} returning {status_code}s"
            if deploy_match:
                mechanism = f"{mechanism} after the {deploy_match.group(1).strip()} deploy"
            incident_props["cause_summary"] = mechanism

    rollback_match = _ROLLBACK_RE.search(text)
    if rollback_match:
        incident_props["resolution_action"] = f"rolled back to {rollback_match.group(1).strip()}"
        if rollback_match.group(2):
            incident_props["resolution_time"] = rollback_match.group(2).strip()

    _append_entity_once(
        result,
        "Incident",
        incident_id,
        properties=incident_props,
        confidence=0.96,
    )

    service_match = _SERVICE_RE.search(text) or symptom_match
    service_name = ""
    if service_match and "Service" in allowed_types:
        service_name = _canonical_service_name(service_match.group(1))
        _append_entity_once(
            result,
            "Service",
            service_name,
            properties={"source_uri": source_uri},
            confidence=0.86,
        )
        _append_relationship_once(
            result,
            incident_id,
            service_name,
            "AFFECTS",
            properties={"evidence": text.strip(), "source_uri": source_uri},
            confidence=0.88,
        )
        _append_relationship_once(
            result,
            incident_id,
            service_name,
            "IMPACTED",
            properties={"evidence": text.strip(), "source_uri": source_uri},
            confidence=0.89,
        )
        if cause_match or symptom_match:
            mechanism = (
                cause_match.group(1).strip()
                if cause_match
                else str(incident_props.get("cause_summary", "")).strip()
            )
            _append_relationship_once(
                result,
                incident_id,
                service_name,
                "CAUSED_BY",
                properties={
                    "mechanism": mechanism,
                    "evidence": text.strip(),
                    "source_uri": source_uri,
                },
                confidence=0.86,
            )

    reporter_match = _REPORTED_BY_RE.search(text)
    if reporter_match and "Team" in allowed_types:
        team_name = _canonical_team_name(reporter_match.group(1))
        _append_entity_once(
            result,
            "Team",
            team_name,
            properties={"source_uri": source_uri},
            confidence=0.94,
        )
        _append_relationship_once(
            result,
            team_name,
            incident_id,
            "REPORTED_BY",
            properties={"evidence": text.strip(), "source_uri": source_uri},
            confidence=0.93,
        )

    lead_match = _LEAD_RE.search(text) or _ON_IT_RE.search(text)
    if lead_match and "Person" in allowed_types:
        lead_name = lead_match.group(1).strip()
        _append_entity_once(
            result,
            "Person",
            lead_name,
            properties={"role_in_incident": "response lead", "source_uri": source_uri},
            confidence=0.95,
        )
        _append_relationship_once(
            result,
            lead_name,
            incident_id,
            "RESPONDED_TO",
            properties={
                "role": "response lead",
                "evidence": text.strip(),
                "source_uri": source_uri,
            },
            confidence=0.94,
        )

    return result


def _parse_extraction(
    data: dict[str, Any],
    *,
    allowed_types: set[str],
    text_hash: str,
    source_uri: str,
) -> ExtractionResult:
    """Parse raw JSON into a validated ExtractionResult.

    Silently drops entities/relationships with unknown types or invalid
    confidence scores rather than failing the entire extraction.
    """
    entities: list[ExtractedEntity] = []
    relationships: list[ExtractedRelationship] = []
    seen_fingerprints: set[str] = set()

    for raw_ent in data.get("entities", []):
        if not isinstance(raw_ent, dict):
            continue
        etype = raw_ent.get("entity_type", "")
        name = raw_ent.get("name", "")
        if not etype or not name:
            continue
        if etype not in allowed_types:
            continue

        conf = float(raw_ent.get("confidence", 0.8))
        conf = max(0.0, min(1.0, conf))

        ent = ExtractedEntity(
            entity_type=etype,
            name=name.strip(),
            properties=raw_ent.get("properties", {}),
            confidence=conf,
        )

        # In-extraction dedup
        if ent.fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(ent.fingerprint)
        entities.append(ent)

    # Build name set for relationship validation
    entity_names = {e.normalized_name for e in entities}

    for raw_rel in data.get("relationships", []):
        if not isinstance(raw_rel, dict):
            continue
        src = raw_rel.get("source_name", "").strip()
        tgt = raw_rel.get("target_name", "").strip()
        rtype = raw_rel.get("rel_type", "")
        rtype = _RELATIONSHIP_TYPE_ALIASES.get(rtype, rtype)
        if not src or not tgt or not rtype:
            continue
        if rtype not in RELATIONSHIP_TYPES:
            continue

        # Only keep relationships where both endpoints were extracted
        if src.lower().strip() not in entity_names or tgt.lower().strip() not in entity_names:
            continue

        conf = float(raw_rel.get("confidence", 0.8))
        conf = max(0.0, min(1.0, conf))

        relationships.append(
            ExtractedRelationship(
                source_name=src,
                target_name=tgt,
                rel_type=rtype,
                properties=raw_rel.get("properties", {}),
                confidence=conf,
            )
        )

    log.info(
        "extraction.parsed",
        entities=len(entities),
        relationships=len(relationships),
        source_uri=source_uri,
    )

    return ExtractionResult(
        entities=entities,
        relationships=relationships,
        source_text_hash=text_hash,
        source_uri=source_uri,
    )
