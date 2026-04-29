"""Background ingest worker — async task queue for Neo4j batch operations.

Decouples large graph ingest batches from the HTTP request/response cycle so
callers get an immediate 202 Accepted and can poll for completion.

Uses a bounded ``asyncio.Queue``; requests above capacity are rejected
immediately with a RuntimeError so the caller can return HTTP 429.

Retry policy: transient failures (connection errors, timeouts) are retried
up to ``_MAX_RETRIES`` times with exponential backoff before marking a job
as permanently FAILED.

Usage::

    worker = get_ingest_worker()
    job_id = worker.enqueue(entities, relationships)   # non-blocking
    job    = worker.get_job(job_id)                    # poll status
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

from aim.schemas.graph import GraphEntity, GraphRelationship

log = structlog.get_logger(__name__)

# Completed/failed jobs are evicted after this many seconds to bound memory use.
_JOB_RETENTION_SECONDS: float = 3600.0
_MAX_RETRIES: int = 3
_RETRY_BASE_DELAY: float = 2.0  # seconds; doubles per attempt


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobKind(StrEnum):
    """Distinguishes graph-only ingest from extraction + ingest."""
    INGEST = "ingest"
    EXTRACTION = "extraction"


@dataclass
class IngestJob:
    job_id: str
    entities: list[GraphEntity]
    relationships: list[GraphRelationship]
    status: JobStatus = JobStatus.QUEUED
    kind: JobKind = JobKind.INGEST
    nodes_merged: int = 0
    rels_created: int = 0
    error: str | None = None
    retries: int = 0
    created_at: float = field(default_factory=time.monotonic)
    completed_at: float | None = None
    api_key_hash: str = ""  # SHA-256 hash of the caller's API key for ownership
    tenant_id: str = ""  # Graph tenant namespace; usually same hash in multi-tenant mode
    # Extraction-specific fields (only used when kind == EXTRACTION)
    raw_text: str = ""
    source_uri: str = ""
    entities_extracted: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status.value,
            "kind": self.kind.value,
            "nodes_merged": self.nodes_merged,
            "rels_created": self.rels_created,
            "error": self.error,
            "retries": self.retries,
            "entities_queued": len(self.entities),
            "relationships_queued": len(self.relationships),
            "completed": self.completed_at is not None,
        }
        if self.kind == JobKind.EXTRACTION:
            d["entities_extracted"] = self.entities_extracted
            d["source_uri"] = self.source_uri
        return d


class IngestWorker:
    """Single-consumer async queue for background Neo4j batch ingest.

    One worker per process is sufficient because Neo4j ingest is I/O-bound
    and the shared driver handles connection pooling internally.
    """

    def __init__(self, maxsize: int = 200) -> None:
        self._queue: asyncio.Queue[IngestJob] = asyncio.Queue(maxsize=maxsize)
        self._jobs: dict[str, IngestJob] = {}
        self._task: asyncio.Task[None] | None = None
        self._draining = False

    @property
    def queue_depth(self) -> int:
        """Current number of jobs waiting in the queue."""
        return self._queue.qsize()

    @property
    def is_alive(self) -> bool:
        """True if the background consumer task is running."""
        return self._task is not None and not self._task.done()

    def enqueue(
        self,
        entities: list[GraphEntity],
        relationships: list[GraphRelationship],
        api_key_hash: str = "",
        tenant_id: str = "",
    ) -> str:
        """Queue a batch for background ingest. Returns the job_id immediately.

        Raises ``RuntimeError`` if the queue is at capacity (caller should
        return HTTP 429 and let the client retry).
        """
        job = IngestJob(
            job_id=str(uuid.uuid4()),
            entities=entities,
            relationships=relationships,
            api_key_hash=api_key_hash,
            tenant_id=tenant_id,
        )
        self._jobs[job.job_id] = job

        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            job.status = JobStatus.FAILED
            job.error = "Ingest queue is at capacity — retry later."
            log.warning("ingest_worker.queue_full", job_id=job.job_id)
            raise RuntimeError(job.error)

        log.info(
            "ingest_worker.enqueued",
            job_id=job.job_id,
            entities=len(entities),
            rels=len(relationships),
        )
        return job.job_id

    def enqueue_extraction(
        self,
        text: str,
        source_uri: str = "",
        api_key_hash: str = "",
        tenant_id: str = "",
    ) -> str:
        """Queue raw text for LLM extraction → dedup → graph ingest.

        The extraction and deduplication happen inside the worker loop,
        so this method returns immediately with a job_id.

        Raises ``RuntimeError`` if the queue is at capacity.
        """
        job = IngestJob(
            job_id=str(uuid.uuid4()),
            entities=[],
            relationships=[],
            kind=JobKind.EXTRACTION,
            raw_text=text,
            source_uri=source_uri,
            api_key_hash=api_key_hash,
            tenant_id=tenant_id,
        )
        self._jobs[job.job_id] = job

        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            job.status = JobStatus.FAILED
            job.error = "Ingest queue is at capacity — retry later."
            log.warning("ingest_worker.queue_full", job_id=job.job_id)
            raise RuntimeError(job.error)

        log.info(
            "ingest_worker.enqueued_extraction",
            job_id=job.job_id,
            source_uri=source_uri,
            text_len=len(text),
        )
        return job.job_id

    def get_job(self, job_id: str) -> IngestJob | None:
        return self._jobs.get(job_id)

    async def start(self) -> None:
        """Start the background consumer task."""
        self._draining = False
        self._task = asyncio.create_task(self._run_loop(), name="ingest_worker")
        log.info("ingest_worker.started")

    async def stop(self, drain_timeout: float = 10.0) -> None:
        """Stop the worker, draining in-flight jobs before cancelling.

        Waits up to ``drain_timeout`` seconds for the current job to finish
        before force-cancelling. Queued jobs remain in QUEUED state.
        """
        self._draining = True
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=drain_timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        log.info("ingest_worker.stopped")

    def _evict_old_jobs(self) -> None:
        """Remove completed/failed jobs older than the retention window.

        Uses ``completed_at`` (not ``created_at``) so that long-running jobs
        aren't evicted immediately after finishing — the retention window
        always starts from when the job reached its terminal state.
        """
        cutoff = time.monotonic() - _JOB_RETENTION_SECONDS
        stale = [
            jid for jid, job in self._jobs.items()
            if job.status in (JobStatus.DONE, JobStatus.FAILED)
            and job.completed_at is not None
            and job.completed_at < cutoff
        ]
        for jid in stale:
            del self._jobs[jid]
        if stale:
            log.debug("ingest_worker.evicted_jobs", count=len(stale))

    async def _run_loop(self) -> None:
        from aim.graph.neo4j_client import Neo4jClient

        while True:
            # If draining and queue is empty, exit cleanly
            if self._draining and self._queue.empty():
                return

            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if self._draining:
                    return
                continue

            job.status = JobStatus.RUNNING
            log.info(
                "ingest_worker.processing",
                job_id=job.job_id,
                kind=job.kind.value,
                entities=len(job.entities),
                rels=len(job.relationships),
            )

            # ── Extraction pre-processing ────────────────────────────────────
            if job.kind == JobKind.EXTRACTION:
                try:
                    job.entities, job.relationships = await self._run_extraction(job)
                except Exception as exc:
                    job.status = JobStatus.FAILED
                    job.completed_at = time.monotonic()
                    job.error = f"Extraction failed: {exc}"
                    log.error(
                        "ingest_worker.extraction_failed",
                        job_id=job.job_id,
                        error=str(exc),
                    )
                    self._queue.task_done()
                    self._evict_old_jobs()
                    continue

            # ── Graph ingest (with retries) ──────────────────────────────────
            success = False
            last_error: Exception | None = None

            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    client = Neo4jClient()
                    nodes, rels = await client.ingest_batch(
                        job.entities,
                        job.relationships,
                        tenant_id=job.tenant_id,
                    )
                    job.nodes_merged = nodes
                    job.rels_created = rels
                    job.status = JobStatus.DONE
                    job.completed_at = time.monotonic()
                    success = True
                    log.info(
                        "ingest_worker.done",
                        job_id=job.job_id,
                        kind=job.kind.value,
                        nodes=nodes,
                        rels=rels,
                        attempts=attempt,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    job.retries = attempt
                    if attempt < _MAX_RETRIES:
                        delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        log.warning(
                            "ingest_worker.retry",
                            job_id=job.job_id,
                            attempt=attempt,
                            max_retries=_MAX_RETRIES,
                            delay=delay,
                            error=str(exc),
                        )
                        await asyncio.sleep(delay)

            if not success:
                job.status = JobStatus.FAILED
                job.completed_at = time.monotonic()
                job.error = type(last_error).__name__ if last_error else "Unknown"
                log.error(
                    "ingest_worker.failed",
                    job_id=job.job_id,
                    error=str(last_error),
                    retries=_MAX_RETRIES,
                )

            self._queue.task_done()
            self._evict_old_jobs()

    async def _run_extraction(
        self, job: IngestJob
    ) -> tuple[list[GraphEntity], list[GraphRelationship]]:
        """Run LLM extraction + deduplication for an extraction job.

        Returns ``(entities, relationships)`` ready for graph ingest.
        """
        from aim.config import get_settings
        from aim.extraction.llm_extractor import get_extractor
        from aim.extraction.deduplicator import get_deduplicator

        settings = get_settings()
        extractor = get_extractor()
        dedup = get_deduplicator()

        entity_types = settings.extraction_entity_types or None
        result = await extractor.extract(
            job.raw_text,
            source_uri=job.source_uri,
            entity_types=entity_types,
        )

        job.entities_extracted = len(result.entities)

        if result.is_empty:
            log.info(
                "ingest_worker.extraction_empty",
                job_id=job.job_id,
                source_uri=job.source_uri,
            )
            return [], []

        entities, relationships = dedup.deduplicate(
            result,
            confidence_threshold=settings.extraction_confidence_threshold,
        )

        # ── δ.1 + δ.2: augment with derived MENTIONS edges ───────────────────
        # Panel audit flagged that MENTIONS only ran at seed time — every
        # live-extracted doc landed as a leaf with no cross-references. The
        # derivation runs in two layers:
        #
        #   δ.1 (in-batch):      union over the newly-extracted entities
        #                        only. Fast; no Neo4j read.
        #   δ.2 (cross-corpus):  union over pre-existing corpus + new batch,
        #                        filter to edges touching a batch entity.
        #                        Makes "Slack msg references already-
        #                        ingested Jira ticket" produce a real edge.
        #
        # Ordering matters: δ.2 runs after δ.1 and reuses whatever new
        # edges δ.1 emitted so δ.2's existing-rel dedup doesn't re-emit
        # them. Failures in δ.2 (e.g. transient Neo4j flake) fall through
        # so at-minimum the in-batch pass still lands.
        if settings.live_ingestion_augment_mentions and entities:
            from aim.utils.mention_extractor import derive_mentions
            # ``derive_mentions`` takes seed-shape dicts; project typed
            # entities through the same shape so the same helper works for
            # both seed-time and live-time callers.
            ent_dicts = [
                {
                    "entity_id": e.entity_id,
                    "labels": e.labels,
                    "properties": e.properties,
                }
                for e in entities
            ]
            rel_dicts = [
                {
                    "source_id": r.source_id,
                    "target_id": r.target_id,
                    "rel_type": r.rel_type,
                    "properties": r.properties,
                }
                for r in relationships
            ]
            derived = derive_mentions(ent_dicts, existing_relationships=rel_dicts)
            for d in derived:
                relationships.append(
                    GraphRelationship(
                        rel_id=f"{d['source_id']}->{d['rel_type']}->{d['target_id']}",
                        rel_type=d["rel_type"],
                        source_id=d["source_id"],
                        target_id=d["target_id"],
                        properties=d.get("properties", {}),
                    )
                )
            log.info(
                "ingest_worker.mentions_augmented",
                job_id=job.job_id,
                derived=len(derived),
            )

            if settings.live_ingestion_cross_corpus_mentions:
                await self._augment_cross_corpus_mentions(
                    job=job,
                    entities=entities,
                    relationships=relationships,
                    batch_ent_dicts=ent_dicts,
                )

        log.info(
            "ingest_worker.extraction_complete",
            job_id=job.job_id,
            extracted_entities=len(result.entities),
            deduped_entities=len(entities),
            relationships=len(relationships),
        )
        return entities, relationships


    async def _augment_cross_corpus_mentions(
        self,
        *,
        job: IngestJob,
        entities: list[GraphEntity],
        relationships: list[GraphRelationship],
        batch_ent_dicts: list[dict[str, Any]],
    ) -> None:
        """δ.2: derive MENTIONS between batch entities and the pre-existing
        Neo4j corpus.

        Mutates ``relationships`` in place — new edges are appended. Edges
        between two pre-existing entities are explicitly excluded: the
        seed/batch worker can derive those at its own cadence, and emitting
        them here would both duplicate work and re-trigger old edges on
        every webhook.

        On any exception we log and return — δ.1's in-batch pass has
        already run, so a Neo4j flake here doesn't leave the job
        un-augmented. The caller's retry loop covers actual ingest_batch
        writes; this is a best-effort enrichment layer.
        """
        from aim.config import get_settings
        from aim.graph.neo4j_client import Neo4jClient
        from aim.utils.mention_extractor import derive_mentions

        settings = get_settings()
        limit = settings.ingestion_cross_corpus_snapshot_limit
        batch_ids = {e.entity_id for e in entities}

        try:
            client = Neo4jClient()
            try:
                existing_entities = await client.list_entity_snapshot(
                    limit=limit,
                    tenant_id=job.tenant_id,
                )
                existing_rels = await client.list_relationship_snapshot(
                    limit=limit * 2,
                    tenant_id=job.tenant_id,
                )
            except TypeError:
                # Compatibility for older test doubles/custom graph clients.
                existing_entities = await client.list_entity_snapshot(limit=limit)
                existing_rels = await client.list_relationship_snapshot(limit=limit * 2)
        except Exception as exc:
            log.warning(
                "ingest_worker.cross_corpus_snapshot_failed",
                job_id=job.job_id,
                error=str(exc),
            )
            return

        # Drop any snapshot entry whose entity_id collides with the batch —
        # otherwise ``derive_mentions`` would see two copies of the same
        # entity and emit duplicate edges on self-matches.
        filtered_existing = [
            e for e in existing_entities if e.get("entity_id") not in batch_ids
        ]

        # Include the δ.1 edges just appended in the dedup set so we don't
        # re-emit them here.
        existing_rels_with_in_batch = list(existing_rels) + [
            {
                "source_id": r.source_id,
                "target_id": r.target_id,
                "rel_type": r.rel_type,
            }
            for r in relationships
        ]

        corpus = filtered_existing + batch_ent_dicts
        try:
            derived = derive_mentions(
                corpus,
                existing_relationships=existing_rels_with_in_batch,
            )
        except Exception as exc:
            log.warning(
                "ingest_worker.cross_corpus_derivation_failed",
                job_id=job.job_id,
                error=str(exc),
            )
            return

        # Only edges touching at least one batch entity — anything between
        # two pre-existing entities was derivable before this job ran and
        # is handled by a separate sweep (not implemented yet; see project
        # memory for the scheduling plan).
        touching = [
            d for d in derived
            if d["source_id"] in batch_ids or d["target_id"] in batch_ids
        ]
        for d in touching:
            relationships.append(
                GraphRelationship(
                    rel_id=f"{d['source_id']}->{d['rel_type']}->{d['target_id']}",
                    rel_type=d["rel_type"],
                    source_id=d["source_id"],
                    target_id=d["target_id"],
                    properties=d.get("properties", {}),
                )
            )
        log.info(
            "ingest_worker.cross_corpus_mentions_augmented",
            job_id=job.job_id,
            corpus_size=len(filtered_existing),
            derived_touching_batch=len(touching),
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_worker_instance: IngestWorker | None = None


def get_ingest_worker() -> IngestWorker:
    """Return the process-wide IngestWorker, creating it lazily."""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = IngestWorker()
    return _worker_instance
