"""Evidence-level access control helpers.

Tenant isolation prevents cross-customer leakage, but an institutional memory
engine also needs artifact-level sovereignty: facts inherited from a private
Slack thread or Jira project should not appear in retrieval or provenance
unless the caller is allowed to see the underlying evidence.
"""
from __future__ import annotations

from typing import Any, Iterable

from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.schemas.provenance import SourceReference

PUBLIC_PRINCIPALS = frozenset({"*", "public", "PUBLIC"})


def principal_scope(
    *,
    tenant_id: str = "",
    api_key_hash: str = "",
    extras: Iterable[str] = (),
) -> list[str]:
    """Build trusted principals for one request."""
    principals = {"public"}
    if tenant_id:
        principals.add(f"tenant:{tenant_id}")
    if api_key_hash:
        principals.add(f"api_key:{api_key_hash}")
    for item in extras:
        if item:
            principals.add(str(item))
    return sorted(principals)


def _as_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {part.strip() for part in value.replace(";", ",").split(",") if part.strip()}
    if isinstance(value, Iterable):
        return {str(part).strip() for part in value if str(part).strip()}
    return {str(value)}


def _allowed_values(metadata: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in (
        "acl_principals",
        "allowed_principals",
        "principals_allowed",
        "acl_groups",
        "allowed_groups",
    ):
        out.update(_as_set(metadata.get(key)))
    return out


def can_access_metadata(
    metadata: dict[str, Any] | None,
    *,
    principals: Iterable[str],
    tenant_id: str = "",
) -> bool:
    """Return whether the caller can see an artifact/entity/source.

    Compatibility rule: data with no ACL fields remains visible. Once ACL
    fields exist, at least one caller principal must match. A tenant_id mismatch
    always denies access.
    """
    if not metadata:
        return True

    md = dict(metadata)
    md_tenant = str(md.get("tenant_id") or "")
    if tenant_id and md_tenant and md_tenant != tenant_id:
        return False

    visibility = str(md.get("visibility") or md.get("access") or "").lower()
    if visibility in {"public", "internal"} and not _allowed_values(md):
        return True
    if visibility in {"private", "restricted"} and not _allowed_values(md):
        return False

    allowed = _allowed_values(md)
    if not allowed:
        return True
    caller = set(principals)
    return bool((allowed & caller) or (allowed & PUBLIC_PRINCIPALS))


def filter_graph_by_access(
    entities: list[GraphEntity],
    relationships: list[GraphRelationship],
    *,
    principals: Iterable[str],
    tenant_id: str = "",
) -> tuple[list[GraphEntity], list[GraphRelationship]]:
    kept_entities = [
        entity for entity in entities
        if can_access_metadata(entity.properties, principals=principals, tenant_id=tenant_id)
    ]
    kept_ids = {entity.entity_id for entity in kept_entities}
    kept_rels = [
        rel for rel in relationships
        if rel.source_id in kept_ids
        and rel.target_id in kept_ids
        and can_access_metadata(rel.properties, principals=principals, tenant_id=tenant_id)
    ]
    return kept_entities, kept_rels


def filter_sources_by_access(
    sources: dict[str, SourceReference],
    *,
    principals: Iterable[str],
    tenant_id: str = "",
) -> dict[str, SourceReference]:
    return {
        source_id: ref
        for source_id, ref in sources.items()
        if can_access_metadata(ref.metadata, principals=principals, tenant_id=tenant_id)
    }


def filter_vector_snippets_by_access(
    snippets: list[dict[str, Any]],
    *,
    principals: Iterable[str],
    tenant_id: str = "",
) -> list[dict[str, Any]]:
    return [
        snippet for snippet in snippets
        if can_access_metadata(snippet, principals=principals, tenant_id=tenant_id)
    ]


def prune_source_map(
    source_map: dict[str, list[str]],
    allowed_source_ids: set[str],
) -> dict[str, list[str]]:
    return {
        query: [source_id for source_id in source_ids if source_id in allowed_source_ids]
        for query, source_ids in source_map.items()
    }
