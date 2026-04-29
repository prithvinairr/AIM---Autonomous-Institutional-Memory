"""Unit tests for the background ingest worker."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.workers.ingest_worker import IngestJob, IngestWorker, JobKind, JobStatus


def _entity(eid: str = "e1") -> GraphEntity:
    return GraphEntity(entity_id=eid, labels=["Test"], properties={"name": eid})


def _rel(src: str = "e1", tgt: str = "e2") -> GraphRelationship:
    return GraphRelationship(
        rel_id="r1", rel_type="RELATES_TO", source_id=src, target_id=tgt, properties={}
    )


# ── Enqueue ──────────────────────────────────────────────────────────────────


def test_enqueue_returns_job_id():
    worker = IngestWorker(maxsize=10)
    job_id = worker.enqueue([_entity()], [])
    assert isinstance(job_id, str)
    job = worker.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.QUEUED


def test_enqueue_raises_when_queue_full():
    worker = IngestWorker(maxsize=1)
    worker.enqueue([_entity()], [])  # fills queue
    with pytest.raises(RuntimeError, match="capacity"):
        worker.enqueue([_entity("e2")], [])


def test_get_job_returns_none_for_unknown_id():
    worker = IngestWorker()
    assert worker.get_job("nonexistent") is None


def test_queue_depth_tracks_pending_jobs():
    worker = IngestWorker(maxsize=10)
    assert worker.queue_depth == 0
    worker.enqueue([_entity()], [])
    assert worker.queue_depth == 1
    worker.enqueue([_entity("e2")], [])
    assert worker.queue_depth == 2


def test_is_alive_false_before_start():
    worker = IngestWorker()
    assert worker.is_alive is False


def test_job_to_dict_contains_all_fields():
    worker = IngestWorker()
    job_id = worker.enqueue([_entity()], [_rel()])
    job = worker.get_job(job_id)
    d = job.to_dict()
    assert d["job_id"] == job_id
    assert d["status"] == "queued"
    assert d["entities_queued"] == 1
    assert d["relationships_queued"] == 1
    assert d["retries"] == 0


# ── Run loop ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_processes_job_successfully():
    worker = IngestWorker(maxsize=10)
    job_id = worker.enqueue([_entity()], [_rel()])

    mock_client = MagicMock()
    mock_client.ingest_batch = AsyncMock(return_value=(1, 1))

    with patch("aim.graph.neo4j_client.Neo4jClient", return_value=mock_client):
        await worker.start()
        # Wait for processing
        await asyncio.sleep(0.3)
        await worker.stop(drain_timeout=2.0)

    job = worker.get_job(job_id)
    assert job.status == JobStatus.DONE
    assert job.nodes_merged == 1
    assert job.rels_created == 1


@pytest.mark.asyncio
async def test_worker_retries_on_transient_failure():
    worker = IngestWorker(maxsize=10)
    job_id = worker.enqueue([_entity()], [])

    mock_client = MagicMock()
    # Fail twice, then succeed
    mock_client.ingest_batch = AsyncMock(
        side_effect=[ConnectionError("down"), ConnectionError("down"), (1, 0)]
    )

    with patch("aim.graph.neo4j_client.Neo4jClient", return_value=mock_client):
        with patch("aim.workers.ingest_worker._RETRY_BASE_DELAY", 0.01):
            await worker.start()
            await asyncio.sleep(1.0)
            await worker.stop(drain_timeout=2.0)

    job = worker.get_job(job_id)
    assert job.status == JobStatus.DONE
    assert job.retries == 2  # failed twice before success on 3rd attempt


@pytest.mark.asyncio
async def test_worker_marks_failed_after_max_retries():
    worker = IngestWorker(maxsize=10)
    job_id = worker.enqueue([_entity()], [])

    mock_client = MagicMock()
    mock_client.ingest_batch = AsyncMock(side_effect=ConnectionError("down"))

    with patch("aim.graph.neo4j_client.Neo4jClient", return_value=mock_client):
        with patch("aim.workers.ingest_worker._RETRY_BASE_DELAY", 0.01):
            await worker.start()
            await asyncio.sleep(1.5)
            await worker.stop(drain_timeout=2.0)

    job = worker.get_job(job_id)
    assert job.status == JobStatus.FAILED
    assert job.error == "ConnectionError"
    assert job.retries == 3


@pytest.mark.asyncio
async def test_worker_is_alive_during_operation():
    worker = IngestWorker(maxsize=10)

    mock_client = MagicMock()
    mock_client.ingest_batch = AsyncMock(return_value=(0, 0))

    with patch("aim.graph.neo4j_client.Neo4jClient", return_value=mock_client):
        await worker.start()
        assert worker.is_alive is True
        await worker.stop(drain_timeout=2.0)
    assert worker.is_alive is False


@pytest.mark.asyncio
async def test_worker_graceful_drain_completes_in_flight_job():
    worker = IngestWorker(maxsize=10)
    job_id = worker.enqueue([_entity()], [])

    async def slow_ingest(*args, **kwargs):
        await asyncio.sleep(0.2)
        return (1, 0)

    mock_client = MagicMock()
    mock_client.ingest_batch = slow_ingest

    with patch("aim.graph.neo4j_client.Neo4jClient", return_value=mock_client):
        await worker.start()
        await asyncio.sleep(0.05)  # Let it start processing
        await worker.stop(drain_timeout=5.0)  # Should wait for completion

    job = worker.get_job(job_id)
    assert job.status == JobStatus.DONE


# ── stop() edge cases (lines 208-213) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_cancels_task_on_drain_timeout():
    """When drain_timeout expires, stop() catches TimeoutError and cancels the task."""
    worker = IngestWorker(maxsize=10)

    # Create a task that blocks forever so drain will time out
    async def block_forever():
        await asyncio.sleep(3600)

    worker._draining = False
    worker._task = asyncio.create_task(block_forever())

    # Use a very short drain_timeout so the test is fast
    await worker.stop(drain_timeout=0.05)

    # Task should be cancelled after stop()
    assert worker._task.done()
    assert worker.is_alive is False


@pytest.mark.asyncio
async def test_stop_when_task_already_done():
    """When the task is already finished, stop() skips wait_for entirely."""
    worker = IngestWorker(maxsize=10)

    # Create a task that finishes immediately
    async def done_immediately():
        return None

    worker._task = asyncio.create_task(done_immediately())
    # Let the task complete
    await asyncio.sleep(0.05)
    assert worker._task.done()

    # stop() should succeed without errors — the done() check means it
    # skips the wait_for / cancel path entirely
    await worker.stop(drain_timeout=1.0)
    assert worker.is_alive is False


@pytest.mark.asyncio
async def test_stop_when_task_is_none():
    """When start() was never called, stop() is a no-op."""
    worker = IngestWorker(maxsize=10)
    assert worker._task is None
    await worker.stop(drain_timeout=1.0)
    assert worker.is_alive is False


# ── Extraction job failure path (lines 261-274) ────────────────────────────


@pytest.mark.asyncio
async def test_extraction_job_failure_marks_job_failed():
    """When _run_extraction() raises, the extraction job is marked FAILED
    and subsequent jobs still get processed."""
    worker = IngestWorker(maxsize=10)
    job_id = worker.enqueue_extraction(
        text="some raw text",
        source_uri="test://doc",
    )

    # Also enqueue a normal ingest job to verify the worker continues
    normal_job_id = worker.enqueue([_entity()], [])

    mock_client = MagicMock()
    mock_client.ingest_batch = AsyncMock(return_value=(1, 0))

    with (
        patch("aim.graph.neo4j_client.Neo4jClient", return_value=mock_client),
        patch.object(
            IngestWorker,
            "_run_extraction",
            new_callable=AsyncMock,
            side_effect=ValueError("LLM extraction exploded"),
        ),
    ):
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop(drain_timeout=2.0)

    extraction_job = worker.get_job(job_id)
    assert extraction_job.status == JobStatus.FAILED
    assert "Extraction failed" in extraction_job.error
    assert extraction_job.completed_at is not None

    # Normal job should still complete
    normal_job = worker.get_job(normal_job_id)
    assert normal_job.status == JobStatus.DONE


# ── _run_extraction() paths (lines 334-371) ────────────────────────────────


@pytest.mark.asyncio
async def test_run_extraction_non_empty_result():
    """_run_extraction with a non-empty result calls extractor and deduplicator,
    returning the deduped entities and relationships."""
    from aim.extraction.schemas import ExtractionResult, ExtractedEntity

    worker = IngestWorker(maxsize=10)
    job = IngestJob(
        job_id="test-extract-1",
        entities=[],
        relationships=[],
        kind=JobKind.EXTRACTION,
        raw_text="Alice owns service Foo.",
        source_uri="test://doc",
    )

    # Fake extraction result (non-empty)
    fake_extracted_entity = ExtractedEntity(
        entity_type="Person", name="Alice", confidence=0.9,
    )
    fake_result = ExtractionResult(
        entities=[fake_extracted_entity],
        relationships=[],
        source_uri="test://doc",
    )
    assert not fake_result.is_empty

    # The deduplicator returns canonical graph types
    deduped_entities = [_entity("alice")]
    deduped_rels = [_rel("alice", "foo")]

    mock_extractor = MagicMock()
    mock_extractor.extract = AsyncMock(return_value=fake_result)

    mock_dedup = MagicMock()
    mock_dedup.deduplicate = MagicMock(return_value=(deduped_entities, deduped_rels))

    mock_settings = MagicMock()
    mock_settings.extraction_entity_types = None
    mock_settings.extraction_confidence_threshold = 0.7

    with (
        patch("aim.config.get_settings", return_value=mock_settings),
        patch("aim.extraction.llm_extractor.get_extractor", return_value=mock_extractor),
        patch("aim.extraction.deduplicator.get_deduplicator", return_value=mock_dedup),
    ):
        entities, relationships = await worker._run_extraction(job)

    assert entities == deduped_entities
    assert relationships == deduped_rels
    assert job.entities_extracted == 1
    mock_extractor.extract.assert_awaited_once()
    mock_dedup.deduplicate.assert_called_once_with(
        fake_result, confidence_threshold=0.7,
    )


@pytest.mark.asyncio
async def test_run_extraction_empty_result():
    """_run_extraction returns ([], []) when the LLM extracts nothing."""
    from aim.extraction.schemas import ExtractionResult

    worker = IngestWorker(maxsize=10)
    job = IngestJob(
        job_id="test-extract-2",
        entities=[],
        relationships=[],
        kind=JobKind.EXTRACTION,
        raw_text="Nothing useful here.",
        source_uri="test://empty",
    )

    # Empty extraction result
    fake_result = ExtractionResult(entities=[], relationships=[])
    assert fake_result.is_empty

    mock_extractor = MagicMock()
    mock_extractor.extract = AsyncMock(return_value=fake_result)

    mock_dedup = MagicMock()

    mock_settings = MagicMock()
    mock_settings.extraction_entity_types = ["Person", "Service"]
    mock_settings.extraction_confidence_threshold = 0.5

    with (
        patch("aim.config.get_settings", return_value=mock_settings),
        patch("aim.extraction.llm_extractor.get_extractor", return_value=mock_extractor),
        patch("aim.extraction.deduplicator.get_deduplicator", return_value=mock_dedup),
    ):
        entities, relationships = await worker._run_extraction(job)

    assert entities == []
    assert relationships == []
    assert job.entities_extracted == 0
    # Deduplicator should never be called when extraction is empty
    mock_dedup.deduplicate.assert_not_called()
