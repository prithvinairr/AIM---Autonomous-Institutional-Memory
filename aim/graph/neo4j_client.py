"""Async Neo4j client — connection pooling, query timeouts, transactional ingest."""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase
from tenacity import retry, stop_after_attempt, wait_exponential

from aim.config import get_settings
from aim.graph.queries import (
    ALL_SHORTEST_PATHS_QUERY,
    DELETE_ENTITY,
    ENTITY_FULLTEXT_SEARCH,
    ENTITY_FULLTEXT_SEARCH_TENANT,
    ENTITY_HYBRID_SEARCH,
    ENTITY_HYBRID_SEARCH_TENANT,
    ENTITY_NAME_LOOKUP,
    ENTITY_NAME_LOOKUP_TENANT,
    EXPAND_NEIGHBOURHOOD,
    EXPAND_NEIGHBOURHOOD_DAMPENED,
    EXPAND_NEIGHBOURHOOD_FILTERED,
    FETCH_ENTITY_BY_ID,
    LIST_ENTITY_SNAPSHOT,
    LIST_RELATIONSHIP_SNAPSHOT,
    SHORTEST_PATH_QUERY,
    UPSERT_ENTITY,
    UPSERT_ENTITY_TENANT,
    UPSERT_RELATIONSHIP,
)
from aim.schemas.graph import GraphEntity, GraphRelationship, GraphSearchResult
from aim.utils.encryption import decrypt_fields, encrypt_fields
from aim.utils.facts import materialize_fact_layer
from aim.utils.metrics import NEO4J_QUERY_LATENCY, NEO4J_RESULTS

log = structlog.get_logger(__name__)

_FULLTEXT_RESERVED_RE = re.compile(r"&&|\|\||[+\-!(){}\[\]^\"~*?:\\/]")


def _safe_fulltext_query(query_text: str) -> str:
    """Strip Lucene operators that make generated sub-queries fail parsing."""
    cleaned = _FULLTEXT_RESERVED_RE.sub(" ", query_text or "")
    return " ".join(cleaned.split()) or "*"


# Singleton driver — shared across all client instances in a process
_driver_instance: AsyncDriver | None = None


def _append_related_entities(
    raw_entities: list[dict[str, Any]],
    raw_rels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Include traversal neighbor nodes so returned edges are not dangling."""
    by_id: dict[str, dict[str, Any]] = {r["entity_id"]: dict(r) for r in raw_entities}
    for rel in raw_rels:
        for prefix, entity_id in (
            ("source", rel.get("source_id")),
            ("target", rel.get("target_id")),
        ):
            if not entity_id or entity_id in by_id:
                continue
            props = rel.get(f"{prefix}_properties") or {}
            by_id[entity_id] = {
                "entity_id": entity_id,
                "labels": rel.get(f"{prefix}_labels") or [],
                "properties": props,
                "score": float(rel.get("score", 0.65)),
            }
    return list(by_id.values())


def _indexable_labels(labels: list[str]) -> list[str]:
    """Ensure every persisted knowledge node participates in Entity indexes."""
    return labels if "Entity" in labels else ["Entity", *labels]


def _get_driver() -> AsyncDriver:
    global _driver_instance
    if _driver_instance is None:
        settings = get_settings()
        _driver_instance = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=50,
            connection_timeout=10.0,
            max_transaction_retry_time=15.0,
        )
    return _driver_instance


class Neo4jClient:
    """Thin async wrapper around the shared Neo4j driver."""

    def __init__(self) -> None:
        self._driver = _get_driver()
        s = get_settings()
        self._database = s.neo4j_database
        self._query_timeout = s.neo4j_query_timeout_seconds
        self._encrypted_fields = s.encrypted_fields

    async def close(self) -> None:
        # Don't close the shared driver here — it's long-lived.
        # Call Neo4jClient.shutdown() at app teardown instead.
        pass

    @classmethod
    async def shutdown(cls) -> None:
        """Close the shared driver. Call once during app lifespan teardown."""
        global _driver_instance
        if _driver_instance:
            await _driver_instance.close()
            _driver_instance = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _search_core(
        self,
        query_text: str,
        limit: int,
        tenant_id: str,
        expand_query: str,
        expand_params: dict[str, Any],
    ) -> GraphSearchResult:
        """Core search logic — fulltext search + graph expansion.

        All public search methods delegate here with different expand queries
        and parameters (standard, filtered, dampened).
        """
        t0 = time.perf_counter()
        search_query = ENTITY_FULLTEXT_SEARCH_TENANT if tenant_id else ENTITY_FULLTEXT_SEARCH
        search_params: dict[str, Any] = {
            "query": _safe_fulltext_query(query_text),
            "limit": limit,
        }
        if tenant_id:
            search_params["tenant_id"] = tenant_id
        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                raw_entities: list[dict[str, Any]] = []
                # Pass via the `parameters` dict — the Cypher uses `$query`
                # as a parameter name and Neo4j's AsyncSession.run() takes
                # `query` as its first positional, so spreading kwargs collides.
                result = await session.run(search_query, parameters=search_params)
                async for record in result:
                    raw_entities.append(dict(record))

                if not raw_entities:
                    NEO4J_QUERY_LATENCY.observe(time.perf_counter() - t0)
                    return GraphSearchResult(entities=[], relationships=[], total_traversed=0)

                top_ids = [r["entity_id"] for r in raw_entities[:5]]
                raw_rels: list[dict[str, Any]] = []
                rel_result = await session.run(
                    expand_query,
                    entity_ids=top_ids,
                    tenant_id=tenant_id,
                    **expand_params,
                )
                async for record in rel_result:
                    raw_rels.append(dict(record))

        NEO4J_QUERY_LATENCY.observe(time.perf_counter() - t0)
        raw_entities = _append_related_entities(raw_entities, raw_rels)

        entities = [
            GraphEntity(
                entity_id=r["entity_id"],
                labels=r.get("labels", []),
                properties=decrypt_fields(r.get("properties", {}), self._encrypted_fields),
                score=float(r.get("score", 1.0)),
            )
            for r in raw_entities
        ]
        relationships = [
            GraphRelationship(
                rel_id=r["rel_id"],
                rel_type=r["rel_type"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                properties=r.get("properties", {}),
            )
            for r in raw_rels
        ]
        NEO4J_RESULTS.observe(len(entities))
        return GraphSearchResult(
            entities=entities,
            relationships=relationships,
            total_traversed=len(entities) + len(relationships),
        )

    async def search(
        self,
        query_text: str,
        entity_types: list[str] | None = None,
        max_depth: int = 2,
        limit: int = 20,
        tenant_id: str = "",
    ) -> GraphSearchResult:
        return await self._search_core(
            query_text, limit, tenant_id,
            expand_query=EXPAND_NEIGHBOURHOOD,
            expand_params={"depth": max_depth},
        )

    async def search_filtered(
        self,
        query_text: str,
        max_depth: int = 2,
        limit: int = 20,
        rel_filter: str = ">",
        tenant_id: str = "",
    ) -> GraphSearchResult:
        """Like search() but uses a custom relationship filter for apoc traversal.

        When ``tenant_id`` is non-empty, only entities belonging to that tenant
        are returned (multi-tenancy isolation).
        """
        return await self._search_core(
            query_text, limit, tenant_id,
            expand_query=EXPAND_NEIGHBOURHOOD_FILTERED,
            expand_params={"depth": max_depth, "rel_filter": rel_filter},
        )

    async def search_dampened(
        self,
        query_text: str,
        max_depth: int = 2,
        limit: int = 20,
        rel_filter: str = "",
        max_degree: int = 25,
        tenant_id: str = "",
    ) -> GraphSearchResult:
        """Like search_filtered() but with hub-node dampening.

        Nodes whose degree exceeds ``max_degree`` are excluded from the
        traversal results (unless they are a query root). This prevents
        god nodes (e.g. Event Bus, degree 38) from flooding results.
        """
        return await self._search_core(
            query_text, limit, tenant_id,
            expand_query=EXPAND_NEIGHBOURHOOD_DAMPENED,
            expand_params={
                "depth": max_depth,
                "rel_filter": rel_filter,
                "max_degree": max_degree,
            },
        )

    async def search_hybrid(
        self,
        query_text: str,
        embedding: list[float],
        max_depth: int = 2,
        limit: int = 20,
        rel_filter: str = "",
        max_degree: int = 25,
        tenant_id: str = "",
    ) -> GraphSearchResult:
        """Hybrid entity search: fulltext UNION vector, then graph expansion.

        Activates the dormant ``entity_embedding_idx`` — now entities can be
        discovered via semantic similarity (e.g. "auth" → "Authentication Service")
        in addition to name-keyword matches. This is the core topology-aware
        retrieval path that genuinely leverages the graph.
        """
        t0 = time.perf_counter()
        hybrid_query = ENTITY_HYBRID_SEARCH_TENANT if tenant_id else ENTITY_HYBRID_SEARCH
        search_params: dict[str, Any] = {
            "query": _safe_fulltext_query(query_text),
            "embedding": embedding,
            "limit": limit,
        }
        if tenant_id:
            search_params["tenant_id"] = tenant_id

        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                raw_entities: list[dict[str, Any]] = []
                try:
                    result = await session.run(hybrid_query, parameters=search_params)
                    async for record in result:
                        raw_entities.append(dict(record))
                except Exception as exc:
                    # Fall back to fulltext-only if vector index not populated
                    log.warning("neo4j.hybrid_fallback", error=str(exc))
                    fallback_q = (
                        ENTITY_FULLTEXT_SEARCH_TENANT
                        if tenant_id
                        else ENTITY_FULLTEXT_SEARCH
                    )
                    fb_params = {
                        "query": _safe_fulltext_query(query_text),
                        "limit": limit,
                    }
                    if tenant_id:
                        fb_params["tenant_id"] = tenant_id
                    result = await session.run(fallback_q, parameters=fb_params)
                    async for record in result:
                        raw_entities.append(dict(record))

                if not raw_entities:
                    NEO4J_QUERY_LATENCY.observe(time.perf_counter() - t0)
                    return GraphSearchResult(entities=[], relationships=[], total_traversed=0)

                top_ids = [r["entity_id"] for r in raw_entities[:5]]
                raw_rels: list[dict[str, Any]] = []
                rel_result = await session.run(
                    EXPAND_NEIGHBOURHOOD_DAMPENED,
                    entity_ids=top_ids,
                    depth=max_depth,
                    rel_filter=rel_filter,
                    max_degree=max_degree,
                    tenant_id=tenant_id,
                )
                async for record in rel_result:
                    raw_rels.append(dict(record))

        NEO4J_QUERY_LATENCY.observe(time.perf_counter() - t0)
        raw_entities = _append_related_entities(raw_entities, raw_rels)
        entities = [
            GraphEntity(
                entity_id=r["entity_id"],
                labels=r.get("labels", []),
                properties=decrypt_fields(r.get("properties", {}), self._encrypted_fields),
                score=float(r.get("score", 1.0)),
            )
            for r in raw_entities
        ]
        relationships = [
            GraphRelationship(
                rel_id=r["rel_id"],
                rel_type=r["rel_type"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                properties=r.get("properties", {}),
            )
            for r in raw_rels
        ]
        NEO4J_RESULTS.observe(len(entities))
        return GraphSearchResult(
            entities=entities,
            relationships=relationships,
            total_traversed=len(entities) + len(relationships),
        )

    async def lookup_entity_name(self, name: str, tenant_id: str = "") -> str | None:
        """Look up an entity's aim_id by name via fulltext search."""
        query = ENTITY_NAME_LOOKUP_TENANT if tenant_id else ENTITY_NAME_LOOKUP
        params: dict[str, Any] = {"name": _safe_fulltext_query(name)}
        if tenant_id:
            params["tenant_id"] = tenant_id
        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                result = await session.run(query, **params)
                record = await result.single()
                if record is None:
                    return None
                return record.get("aim_id")

    async def search_exact_name(
        self,
        name: str,
        *,
        limit: int = 5,
        rel_limit: int = 40,
        tenant_id: str = "",
    ) -> GraphSearchResult:
        """Return exact name matches plus their immediate factual neighborhood.

        Match strategy (in priority order, all case-insensitive):
        1. Exact match on n.name or n.incident_id (the historical strict mode)
        2. n.name STARTS WITH the query — catches "INC-2025-015" matching
           the real entity "INC-2025-015: Payment Double-Charge". Without
           this, every ID-style query that mentions just the prefix
           returned 0 entities and the agent fell through to no-evidence
           refusal even though the entity was right there.
        """
        entity_query = """
        MATCH (n)
        WHERE toLower(toString(n.name)) = toLower($name)
           OR toLower(toString(n.incident_id)) = toLower($name)
           OR toLower(toString(n.name)) STARTS WITH toLower($name)
        WITH n
        WHERE $tenant_id = "" OR n.tenant_id = $tenant_id
        ORDER BY CASE WHEN n.summary IS NULL THEN 1 ELSE 0 END,
                 coalesce(n.updated_at, n.created_at, n.source_uri, "") DESC
        LIMIT $limit
        RETURN
            coalesce(n.aim_id, elementId(n)) AS entity_id,
            labels(n) AS labels,
            properties(n) AS properties,
            1.0 AS score
        """
        rel_query = """
        MATCH (root)
        WHERE root.aim_id IN $entity_ids OR elementId(root) IN $entity_ids
        MATCH (root)-[r]-(other)
        WHERE type(r) IN $rel_types
          AND ($tenant_id = "" OR other.tenant_id = $tenant_id)
        RETURN
            elementId(r) AS rel_id,
            type(r) AS rel_type,
            coalesce(startNode(r).aim_id, elementId(startNode(r))) AS source_id,
            coalesce(endNode(r).aim_id, elementId(endNode(r))) AS target_id,
            properties(r) AS properties,
            labels(startNode(r)) AS source_labels,
            properties(startNode(r)) AS source_properties,
            labels(endNode(r)) AS target_labels,
            properties(endNode(r)) AS target_properties,
            0.95 AS score
        LIMIT $rel_limit
        """
        rel_types = [
            "AFFECTS",
            "ASSERTS",
            "CAUSED_BY",
            "IMPACTED",
            "LED_TO",
            "OBJECT",
            "RESOLVED_BY",
            "RESPONDED_TO",
            "SUBJECT",
            "SUPERSEDES",
        ]
        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                raw_entities: list[dict[str, Any]] = []
                result = await session.run(
                    entity_query,
                    name=name,
                    limit=limit,
                    tenant_id=tenant_id,
                )
                async for record in result:
                    raw_entities.append(dict(record))

                if not raw_entities:
                    return GraphSearchResult(entities=[], relationships=[], total_traversed=0)

                entity_ids = [r["entity_id"] for r in raw_entities]
                raw_rels: list[dict[str, Any]] = []
                rel_result = await session.run(
                    rel_query,
                    entity_ids=entity_ids,
                    rel_types=rel_types,
                    rel_limit=rel_limit,
                    tenant_id=tenant_id,
                )
                async for record in rel_result:
                    raw_rels.append(dict(record))

        raw_entities = _append_related_entities(raw_entities, raw_rels)
        entities = [
            GraphEntity(
                entity_id=r["entity_id"],
                labels=r.get("labels", []),
                properties=decrypt_fields(r.get("properties", {}), self._encrypted_fields),
                score=float(r.get("score", 1.0)),
            )
            for r in raw_entities
        ]
        relationships = [
            GraphRelationship(
                rel_id=r["rel_id"],
                rel_type=r["rel_type"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                properties=r.get("properties", {}),
            )
            for r in raw_rels
        ]
        return GraphSearchResult(
            entities=entities,
            relationships=relationships,
            total_traversed=len(entities) + len(relationships),
        )

    async def get_entity(self, entity_id: str) -> GraphEntity | None:
        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                result = await session.run(FETCH_ENTITY_BY_ID, entity_id=entity_id)
                record = await result.single()
                if record is None:
                    return None
                return GraphEntity(
                    entity_id=record["entity_id"],
                    labels=record.get("labels", []),
                    properties=decrypt_fields(record.get("properties", {}), self._encrypted_fields),
                )

    async def list_entity_snapshot(
        self,
        limit: int = 10_000,
        tenant_id: str = "",
    ) -> list[dict[str, Any]]:
        """Bounded read of every entity in the graph.

        Returns a list of ``{entity_id, labels, properties}`` dicts in the
        shape expected by :func:`aim.utils.mention_extractor.derive_mentions`.

        Used by the ingest worker to union the pre-existing corpus with the
        newly-extracted batch before deriving MENTIONS — without this, a
        Slack message that references an already-ingested Jira ticket has no
        cross-link in the graph and every traversal has to fall back to the
        synthesizer's regex ticket pass.

        The ``limit`` is bounded so a single webhook can't DoS Neo4j by
        materialising an unbounded result set. For deployments beyond 10k
        entities, wire this through a periodic sweep or an incremental
        index rather than per-event reads.
        """
        out: list[dict[str, Any]] = []
        async with asyncio.timeout(self._query_timeout * 2):
            async with self._driver.session(database=self._database) as session:
                result = await session.run(
                    LIST_ENTITY_SNAPSHOT,
                    limit=limit,
                    tenant_id=tenant_id,
                )
                async for record in result:
                    out.append(
                        {
                            "entity_id": record["entity_id"],
                            "labels": list(record.get("labels") or []),
                            "properties": decrypt_fields(
                                dict(record.get("properties") or {}),
                                self._encrypted_fields,
                            ),
                        }
                    )
        return out

    async def list_relationship_snapshot(
        self,
        limit: int = 20_000,
        tenant_id: str = "",
    ) -> list[dict[str, Any]]:
        """Bounded read of every relationship. Shape matches
        :class:`aim.utils.mention_extractor.derive_mentions`' existing-rel
        dedup input so the ingest worker can suppress already-present edges.
        """
        out: list[dict[str, Any]] = []
        async with asyncio.timeout(self._query_timeout * 2):
            async with self._driver.session(database=self._database) as session:
                result = await session.run(
                    LIST_RELATIONSHIP_SNAPSHOT,
                    limit=limit,
                    tenant_id=tenant_id,
                )
                async for record in result:
                    out.append(
                        {
                            "source_id": record["source_id"],
                            "target_id": record["target_id"],
                            "rel_type": record["rel_type"],
                        }
                    )
        return out

    async def ingest_batch(
        self,
        entities: list[GraphEntity],
        relationships: list[GraphRelationship],
        tenant_id: str = "",
    ) -> tuple[int, int]:
        """Upsert all entities + relationships in a single Neo4j transaction.

        When ``tenant_id`` is non-empty, each entity is stamped with the
        tenant_id property for multi-tenant isolation.

        Returns (nodes_merged, rels_created). Rolls back atomically on failure.
        """
        entities, relationships = materialize_fact_layer(entities, relationships)
        nodes_merged = rels_created = 0
        upsert_query = UPSERT_ENTITY_TENANT if tenant_id else UPSERT_ENTITY

        async with asyncio.timeout(self._query_timeout * 3):  # longer for bulk ops
            async with self._driver.session(database=self._database) as session:
                async with await session.begin_transaction() as tx:
                    try:
                        for entity in entities:
                            params: dict[str, Any] = {
                                "entity_id": entity.entity_id,
                                "labels": _indexable_labels(entity.labels),
                            "properties": encrypt_fields(
                                entity.properties,
                                self._encrypted_fields,
                            ),
                            }
                            if tenant_id:
                                params["tenant_id"] = tenant_id
                            await tx.run(upsert_query, **params)
                            nodes_merged += 1

                        for rel in relationships:
                            await tx.run(
                                UPSERT_RELATIONSHIP,
                                source_id=rel.source_id,
                                target_id=rel.target_id,
                                rel_type=rel.rel_type,
                                properties=rel.properties,
                            )
                            rels_created += 1

                        await tx.commit()
                        log.info(
                            "neo4j.batch_committed",
                            nodes=nodes_merged,
                            rels=rels_created,
                        )
                    except Exception as exc:
                        await tx.rollback()
                        log.error("neo4j.batch_rolled_back", error=str(exc))
                        raise

        return nodes_merged, rels_created

    # Keep individual methods for single-item ops
    async def upsert_entity(self, entity: GraphEntity) -> None:
        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                await session.run(
                    UPSERT_ENTITY,
                    entity_id=entity.entity_id,
                    labels=_indexable_labels(entity.labels),
                    properties=encrypt_fields(entity.properties, self._encrypted_fields),
                )

    async def upsert_relationship(self, rel: GraphRelationship) -> None:
        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                await session.run(
                    UPSERT_RELATIONSHIP,
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    rel_type=rel.rel_type,
                    properties=rel.properties,
                )

    async def find_paths(
        self,
        source_aim_id: str,
        target_aim_id: str,
        all_shortest: bool = False,
        tenant_id: str = "",
    ) -> list[dict[str, Any]]:
        """Find shortest path(s) between two entities by aim_id.

        Returns a list of path dicts, each with:
          - path_nodes: list of {entity_id, aim_id, labels, name}
          - path_rels: list of {rel_id, rel_type, source_id, target_id}
          - hops: int
        """
        query = ALL_SHORTEST_PATHS_QUERY if all_shortest else SHORTEST_PATH_QUERY
        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                result = await session.run(
                    query,
                    source_aim_id=source_aim_id,
                    target_aim_id=target_aim_id,
                    tenant_id=tenant_id,
                )
                paths = []
                async for record in result:
                    paths.append({
                        "path_nodes": record["path_nodes"],
                        "path_rels": record["path_rels"],
                        "hops": record["hops"],
                    })
                return paths

    async def delete_entity(self, entity_id: str) -> bool:
        async with asyncio.timeout(self._query_timeout):
            async with self._driver.session(database=self._database) as session:
                result = await session.run(DELETE_ENTITY, entity_id=entity_id)
                summary = await result.consume()
                return summary.counters.nodes_deleted > 0

    async def health_check(self) -> bool:
        try:
            async with asyncio.timeout(3.0):
                async with self._driver.session(database=self._database) as session:
                    result = await session.run("RETURN 1 AS ok")
                    await result.single()
            return True
        except Exception as exc:
            log.error("neo4j.health_check_failed", error=str(exc))
            return False
