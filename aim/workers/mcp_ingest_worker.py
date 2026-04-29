"""MCP streaming ingest worker.

Polls upstream MCP providers for new content via ``resources/list`` +
``resources/read``, extracts entities/relationships using the LLM extractor,
deduplicates, and upserts into Neo4j + vector store.

Also tails the ``aim:webhook_events`` Redis stream for real-time webhook
events, resolving full context via ``resources/read`` before extraction.

Configuration::

    MCP_INGEST_ENABLED=true
    MCP_INGEST_INTERVAL_SECONDS=300   # polling interval per provider

Idempotency: every source artifact keys on ``aim_id = sha256(source_uri)``.
Re-processing the same Slack message is a no-op because Neo4j MERGEs on aim_id.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import structlog

from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.schemas.mcp import MCPProviderType

if TYPE_CHECKING:
    from aim.mcp.handler import MCPHandler

log = structlog.get_logger(__name__)

_CURSOR_KEY_PREFIX = "aim:ingest_cursor"
_WEBHOOK_STREAM = "aim:webhook_events"


def _stable_id(*parts: str, prefix: str = "") -> str:
    raw = ":".join(p for p in parts if p)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{prefix}{digest}" if prefix else digest


def _text_from_generic_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return str(item)
    return (
        item.get("body_text")
        or item.get("description")
        or item.get("text")
        or item.get("summary")
        or str(item)
    )


def _iter_source_items(
    *,
    provider: str,
    resource_uri: str,
    data: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Flatten MCP context payloads into durable source artifact candidates."""
    for ctx in data.get("data", []):
        if not isinstance(ctx, dict):
            text = _text_from_generic_item(ctx)
            yield {
                "provider": provider,
                "native_id": _stable_id(resource_uri, text),
                "uri": resource_uri,
                "title": resource_uri,
                "text": text,
                "metadata": {},
            }
            continue

        messages = ctx.get("messages")
        if isinstance(messages, list):
            channel = str(ctx.get("channel") or "")
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                native_id = str(
                    msg.get("message_id")
                    or msg.get("ts")
                    or msg.get("timestamp")
                    or _stable_id(resource_uri, _text_from_generic_item(msg))
                )
                uri = msg.get("permalink") or f"slack://channel/{channel}/{native_id}"
                author = msg.get("author") or msg.get("user") or "unknown"
                text = str(msg.get("text") or "")
                yield {
                    "provider": "slack",
                    "native_id": native_id,
                    "uri": str(uri),
                    "title": f"Slack #{channel} {native_id}",
                    "text": f"[Slack #{channel}] {author}: {text}",
                    "metadata": {
                        "channel": channel,
                        "author": author,
                        "thread_ts": msg.get("thread_ts"),
                        "created_at": msg.get("timestamp"),
                        "permalink": msg.get("permalink"),
                    },
                }
            continue

        issues = ctx.get("issues")
        if isinstance(issues, list):
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                native_id = str(issue.get("issue_key") or issue.get("key") or "")
                if not native_id:
                    native_id = _stable_id(resource_uri, _text_from_generic_item(issue))
                uri = issue.get("url") or f"jira://issue/{native_id}"
                summary = str(issue.get("summary") or native_id)
                description = str(issue.get("description") or "")
                yield {
                    "provider": "jira",
                    "native_id": native_id,
                    "uri": str(uri),
                    "title": f"Jira {native_id}: {summary}",
                    "text": f"[Jira {native_id}] {summary}\n{description}",
                    "metadata": {
                        "issue_key": native_id,
                        "status": issue.get("status"),
                        "assignee": issue.get("assignee"),
                        "reporter": issue.get("reporter"),
                        "created_at": issue.get("created_at"),
                        "updated_at": issue.get("updated_at"),
                    },
                }
            continue

        pages = ctx.get("pages")
        if isinstance(pages, list):
            for page in pages:
                if not isinstance(page, dict):
                    continue
                native_id = str(page.get("page_id") or page.get("id") or "")
                title = str(page.get("title") or native_id or "Confluence page")
                text = str(page.get("body_text") or page.get("text") or "")
                uri = page.get("url") or f"confluence://page/{native_id or _stable_id(title, text)}"
                yield {
                    "provider": "confluence",
                    "native_id": native_id or _stable_id(title, text),
                    "uri": str(uri),
                    "title": f"Confluence {title}",
                    "text": f"[Confluence] {title}\n{text}",
                    "metadata": {
                        "space_key": page.get("space_key"),
                        "created_at": page.get("created_at"),
                        "updated_at": page.get("updated_at"),
                    },
                }
            continue

        text = _text_from_generic_item(ctx)
        yield {
            "provider": provider,
            "native_id": str(ctx.get("id") or ctx.get("key") or _stable_id(resource_uri, text)),
            "uri": str(ctx.get("uri") or ctx.get("url") or resource_uri),
            "title": str(ctx.get("title") or ctx.get("name") or resource_uri),
            "text": text,
            "metadata": ctx,
        }


def _source_artifact(item: dict[str, Any]) -> GraphEntity:
    provider = str(item.get("provider") or "mcp")
    native_id = str(item.get("native_id") or "")
    text = str(item.get("text") or "")
    metadata = dict(item.get("metadata") or {})
    props = {
        "name": item.get("title") or item.get("uri"),
        "provider": provider,
        "native_id": native_id,
        "source_uri": item.get("uri"),
        "source_text_hash": hashlib.sha256(text.encode()).hexdigest(),
        "content_excerpt": text[:1000],
        **{k: v for k, v in metadata.items() if v is not None},
    }
    label = {
        "slack": "SlackMessage",
        "jira": "JiraIssue",
        "confluence": "ConfluencePage",
    }.get(provider, "MCPArtifact")
    return GraphEntity(
        entity_id=_stable_id(str(item.get("uri") or provider), prefix="source:"),
        labels=["Entity", "SourceArtifact", label],
        properties=props,
        score=1.0,
    )


class MCPIngestWorker:
    """Long-running async worker that polls MCP providers for fresh content."""

    def __init__(self) -> None:
        from aim.config import get_settings
        self._settings = get_settings()
        self._interval = self._settings.mcp_ingest_interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None
        self._providers = [MCPProviderType.SLACK, MCPProviderType.JIRA]

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="mcp_ingest_worker")
        log.info("mcp_ingest.started", interval=self._interval)

    async def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("mcp_ingest.stopped")

    async def _run(self) -> None:
        """Main polling loop with jittered intervals."""
        import random
        while self._running:
            try:
                await self._poll_all_providers()
                await self._tail_webhook_stream()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("mcp_ingest.cycle_error", error=str(exc))

            # Jittered sleep to avoid thundering herd
            jitter = random.uniform(0.8, 1.2)
            await asyncio.sleep(self._interval * jitter)

    async def _poll_all_providers(self) -> None:
        """Poll each registered MCP provider for new resources."""
        from aim.mcp.handler import MCPHandler

        handler = MCPHandler()
        resources = handler.list_resources()

        for resource in resources:
            try:
                await self._ingest_resource(handler, resource.uri)
            except Exception as exc:
                log.warning(
                    "mcp_ingest.resource_error",
                    uri=resource.uri,
                    error=str(exc),
                )

    async def _ingest_resource(self, handler: "MCPHandler", uri: str) -> None:
        """Read a single resource and extract entities."""
        # Check cursor to avoid re-processing
        cursor = await self._get_cursor(uri)

        data = await handler.read_resource(uri)
        items = data.get("data", [])
        if not items:
            return

        # Extract entities from raw content
        from aim.extraction.llm_extractor import get_extractor
        from aim.extraction.deduplicator import get_deduplicator

        extractor = get_extractor()
        deduplicator = get_deduplicator()

        provider = str(data.get("provider") or uri.split(":", 1)[0] or "mcp")

        for item in _iter_source_items(provider=provider, resource_uri=uri, data=data):
            text = str(item.get("text") or "")
            if len(text) < 20:
                continue

            artifact = _source_artifact(item)
            source_uri = str(item.get("uri") or uri)

            try:
                result = await extractor.extract(text, source_uri=source_uri)
                if not result.entities and not result.relationships:
                    from aim.workers.ingest_worker import get_ingest_worker
                    worker = get_ingest_worker()
                    worker.enqueue(entities=[artifact], relationships=[])
                    continue

                # Deduplicate against existing graph
                entities, relationships = deduplicator.deduplicate(result)
                enriched_entities = [artifact, *entities]
                enriched_relationships: list[GraphRelationship] = []
                for rel in relationships:
                    enriched_relationships.append(
                        rel.model_copy(
                            update={
                                "properties": {
                                    **(rel.properties or {}),
                                    "evidence_artifact_id": artifact.entity_id,
                                    "evidence_uri": source_uri,
                                }
                            }
                        )
                    )
                for entity in entities:
                    enriched_relationships.append(
                        GraphRelationship(
                            rel_id=f"{artifact.entity_id}->EVIDENCES->{entity.entity_id}",
                            rel_type="EVIDENCES",
                            source_id=artifact.entity_id,
                            target_id=entity.entity_id,
                            properties={
                                "source_uri": source_uri,
                                "evidence_artifact_id": artifact.entity_id,
                            },
                        )
                    )
                # Upsert via the existing ingest worker
                from aim.workers.ingest_worker import get_ingest_worker
                worker = get_ingest_worker()
                worker.enqueue(
                    entities=enriched_entities,
                    relationships=enriched_relationships,
                )

                log.debug(
                    "mcp_ingest.extracted",
                    uri=source_uri,
                    artifact_id=artifact.entity_id,
                    entities=len(enriched_entities),
                    rels=len(enriched_relationships),
                )
            except Exception as exc:
                log.warning("mcp_ingest.extract_error", uri=uri, error=str(exc))

        # Update cursor
        await self._set_cursor(uri, str(time.time()))

    async def _tail_webhook_stream(self) -> None:
        """Tail the Redis webhook event stream for real-time ingestion."""
        try:
            from aim.utils.cache import get_response_cache
            cache = get_response_cache()
            if cache._redis is None:
                return

            # Read new events from the stream (non-blocking, last 10)
            events = await cache._redis.xread(
                {_WEBHOOK_STREAM: "0-0"},
                count=10,
                block=1000,  # 1s block
            )

            if not events:
                return

            from aim.mcp.handler import MCPHandler
            handler = MCPHandler()

            for _stream, messages in events:
                for msg_id, data in messages:
                    uri = data.get(b"source_uri", b"").decode()
                    if uri:
                        try:
                            await self._ingest_resource(handler, uri)
                        except Exception as exc:
                            log.warning("mcp_ingest.webhook_error", uri=uri, error=str(exc))

                    # Acknowledge by trimming (keep last 1000)
                    await cache._redis.xtrim(_WEBHOOK_STREAM, maxlen=1000)

        except Exception as exc:
            log.debug("mcp_ingest.stream_error", error=str(exc))

    async def _get_cursor(self, uri: str) -> str | None:
        """Get the last-processed cursor for a resource."""
        try:
            from aim.utils.cache import get_response_cache
            cache = get_response_cache()
            if cache._redis is None:
                return None
            key = f"{_CURSOR_KEY_PREFIX}:{hashlib.sha256(uri.encode()).hexdigest()[:16]}"
            val = await cache._redis.get(key)
            return val.decode() if val else None
        except Exception:
            return None

    async def _set_cursor(self, uri: str, cursor: str) -> None:
        """Store the cursor for a resource."""
        try:
            from aim.utils.cache import get_response_cache
            cache = get_response_cache()
            if cache._redis is None:
                return
            key = f"{_CURSOR_KEY_PREFIX}:{hashlib.sha256(uri.encode()).hexdigest()[:16]}"
            await cache._redis.set(key, cursor, ex=86400 * 30)  # 30 day TTL
        except Exception:
            pass


# ── Singleton ────────────────────────────────────────────────────────────────

_worker: MCPIngestWorker | None = None


def get_mcp_ingest_worker() -> MCPIngestWorker:
    global _worker
    if _worker is None:
        _worker = MCPIngestWorker()
    return _worker


def reset_mcp_ingest_worker() -> None:
    global _worker
    _worker = None
