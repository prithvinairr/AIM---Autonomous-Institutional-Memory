"""Live ingestion — incremental writes into Neo4j + derivation of
cross-entity MENTIONS edges at the moment a new document lands.

Seed ingestion (``aim/scripts/seed_demo.py``) is batch-time: the whole
corpus is loaded, derivation runs once, and that's the only moment
MENTIONS edges come into existence. Live ingestion fills the gap — when
Slack/Jira/Confluence emit a new document during normal operation, the
worker here promotes textual references into first-class graph edges
so the next query traversal can follow them.

The public surface is small on purpose:

* :func:`prepare_ingestion` — pure function. Given a new entity and the
  existing corpus, returns the entity unchanged plus a list of derived
  MENTIONS edges (dedup'd against ``existing_relationships``). No I/O,
  fully unit-testable.
* :func:`ingest_document` — async coroutine. Wraps ``prepare_ingestion``
  with the Neo4j upsert calls. The pure + impure split is deliberate so
  tests don't need a live DB for the derivation contract.
"""
from aim.ingestion.live_worker import ingest_document, prepare_ingestion

__all__ = ["ingest_document", "prepare_ingestion"]
