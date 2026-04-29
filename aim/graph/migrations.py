"""Neo4j schema migrations — versioned, idempotent, self-tracking.

Each migration is applied exactly once and recorded as a ``__AIMSchemaVersion``
node inside the graph itself, so the database self-documents its schema state.

Rules:
  - NEVER reorder or remove migrations — only append new ones.
  - Every migration must be idempotent (use IF NOT EXISTS / MERGE / CONSTRAINT
    ... IF NOT EXISTS) so a retry after a partial failure is safe.
  - Schema commands (CREATE INDEX / CONSTRAINT) cannot be wrapped in an
    explicit Neo4j transaction; they auto-commit and are NOT rolled back on
    failure.  If a migration fails, fix the Cypher and re-deploy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from neo4j import AsyncDriver

log = structlog.get_logger(__name__)

_VERSION_LABEL = "__AIMSchemaVersion"


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    cypher: str


# ── Migration registry — APPEND ONLY ─────────────────────────────────────────

MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        description="Fulltext index on Entity nodes (name, description, title, content)",
        cypher="""
        CREATE FULLTEXT INDEX entity_fulltext_idx IF NOT EXISTS
        FOR (n:Entity)
        ON EACH [n.name, n.description, n.title, n.content]
        OPTIONS { indexConfig: { `fulltext.analyzer`: 'english' } }
        """,
    ),
    Migration(
        version=2,
        description="Vector index for 1536-dim cosine embedding search",
        cypher="""
        CREATE VECTOR INDEX entity_embedding_idx IF NOT EXISTS
        FOR (n:Entity) ON (n.embedding)
        OPTIONS {
            indexConfig: {
                `vector.dimensions`: 1536,
                `vector.similarity_function`: 'cosine'
            }
        }
        """,
    ),
    Migration(
        version=3,
        description="Uniqueness constraint on aim_id property",
        cypher="""
        CREATE CONSTRAINT entity_aim_id_unique IF NOT EXISTS
        FOR (n:Entity) REQUIRE n.aim_id IS UNIQUE
        """,
    ),
]


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_applied_versions(session) -> set[int]:
    result = await session.run(
        f"MATCH (v:{_VERSION_LABEL}) RETURN v.version AS version"
    )
    versions: set[int] = set()
    async for record in result:
        versions.add(record["version"])
    return versions


# ── Public API ────────────────────────────────────────────────────────────────

async def run_migrations(driver: "AsyncDriver", database: str) -> int:
    """Run all pending schema migrations. Returns the count of migrations applied.

    Safe to call on every startup — already-applied migrations are skipped.
    The migration version table is created lazily on the first run.
    """
    applied = 0

    async with driver.session(database=database) as session:
        try:
            existing = await _get_applied_versions(session)
        except Exception:
            # Brand-new database — version tracking node doesn't exist yet.
            existing = set()

        pending = [m for m in MIGRATIONS if m.version not in existing]

        if not pending:
            log.info("neo4j.migrations_up_to_date", total=len(MIGRATIONS))
            return 0

        log.info("neo4j.migrations_pending", count=len(pending))

        for migration in pending:
            log.info(
                "neo4j.migration_applying",
                version=migration.version,
                description=migration.description,
            )
            try:
                # Schema commands auto-commit — run outside explicit tx.
                await session.run(migration.cypher)
                # Record the applied version.
                await session.run(
                    f"""
                    MERGE (v:{_VERSION_LABEL} {{version: $version}})
                    SET v.description = $description,
                        v.applied_at  = datetime()
                    """,
                    version=migration.version,
                    description=migration.description,
                )
                applied += 1
                log.info("neo4j.migration_applied", version=migration.version)

            except Exception as exc:
                log.error(
                    "neo4j.migration_failed",
                    version=migration.version,
                    error=str(exc),
                )
                raise RuntimeError(
                    f"Neo4j migration v{migration.version} failed: {exc}"
                ) from exc

    log.info("neo4j.migrations_complete", applied=applied, total=len(MIGRATIONS))
    return applied
