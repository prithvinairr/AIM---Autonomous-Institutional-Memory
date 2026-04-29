"""Cypher query templates for AIM knowledge graph operations."""

# ── Search ────────────────────────────────────────────────────────────────────

ENTITY_FULLTEXT_SEARCH = """
CALL db.index.fulltext.queryNodes('entity_fulltext_idx', $query)
YIELD node, score
WITH node, score
ORDER BY score DESC
LIMIT $limit
RETURN
    coalesce(node.aim_id, elementId(node)) AS entity_id,
    labels(node)             AS labels,
    properties(node)         AS properties,
    score                    AS score
"""

# Tenant-scoped variant: only returns entities belonging to the caller's tenant.
ENTITY_FULLTEXT_SEARCH_TENANT = """
CALL db.index.fulltext.queryNodes('entity_fulltext_idx', $query)
YIELD node, score
WITH node, score
WHERE node.tenant_id = $tenant_id
ORDER BY score DESC
LIMIT $limit
RETURN
    coalesce(node.aim_id, elementId(node)) AS entity_id,
    labels(node)             AS labels,
    properties(node)         AS properties,
    score                    AS score
"""

EXPAND_NEIGHBOURHOOD = """
MATCH (root)
WHERE root.aim_id IN $entity_ids OR elementId(root) IN $entity_ids
CALL apoc.path.subgraphAll(root, {
    maxLevel: $depth
})
YIELD nodes, relationships
WITH nodes, relationships
WHERE $tenant_id = "" OR all(n IN nodes WHERE n.tenant_id = $tenant_id)
UNWIND relationships AS r
RETURN
    elementId(r)             AS rel_id,
    type(r)                  AS rel_type,
    coalesce(startNode(r).aim_id, elementId(startNode(r)))  AS source_id,
    coalesce(endNode(r).aim_id, elementId(endNode(r)))      AS target_id,
    properties(r)            AS properties,
    labels(startNode(r))     AS source_labels,
    properties(startNode(r)) AS source_properties,
    labels(endNode(r))       AS target_labels,
    properties(endNode(r))   AS target_properties
"""

EXPAND_NEIGHBOURHOOD_FILTERED = """
MATCH (root)
WHERE root.aim_id IN $entity_ids OR elementId(root) IN $entity_ids
CALL apoc.path.subgraphAll(root, {
    maxLevel: $depth,
    relationshipFilter: $rel_filter
})
YIELD nodes, relationships
WITH nodes, relationships
WHERE $tenant_id = "" OR all(n IN nodes WHERE n.tenant_id = $tenant_id)
UNWIND relationships AS r
RETURN
    elementId(r)             AS rel_id,
    type(r)                  AS rel_type,
    coalesce(startNode(r).aim_id, elementId(startNode(r)))  AS source_id,
    coalesce(endNode(r).aim_id, elementId(endNode(r)))      AS target_id,
    properties(r)            AS properties,
    labels(startNode(r))     AS source_labels,
    properties(startNode(r)) AS source_properties,
    labels(endNode(r))       AS target_labels,
    properties(endNode(r))   AS target_properties
"""

# Hub-dampened variant: filters out high-degree nodes during traversal
# to prevent god nodes (e.g. Event Bus, degree 38) from drowning results.
# Root nodes are never filtered — only their high-degree neighbours.
EXPAND_NEIGHBOURHOOD_DAMPENED = """
MATCH (root)
WHERE root.aim_id IN $entity_ids OR elementId(root) IN $entity_ids
CALL apoc.path.subgraphAll(root, {
    maxLevel: $depth,
    relationshipFilter: $rel_filter
})
YIELD nodes, relationships
WITH nodes, relationships, $entity_ids AS root_ids
WHERE $tenant_id = "" OR all(n IN nodes WHERE n.tenant_id = $tenant_id)
UNWIND nodes AS n
WITH n, relationships, root_ids,
     COUNT { (n)--() } AS degree
WHERE degree <= $max_degree OR n.aim_id IN root_ids OR elementId(n) IN root_ids
WITH collect(DISTINCT n) AS kept, relationships
UNWIND relationships AS r
WITH r, kept
WHERE startNode(r) IN kept AND endNode(r) IN kept
RETURN
    elementId(r)             AS rel_id,
    type(r)                  AS rel_type,
    coalesce(startNode(r).aim_id, elementId(startNode(r)))  AS source_id,
    coalesce(endNode(r).aim_id, elementId(endNode(r)))      AS target_id,
    properties(r)            AS properties,
    labels(startNode(r))     AS source_labels,
    properties(startNode(r)) AS source_properties,
    labels(endNode(r))       AS target_labels,
    properties(endNode(r))   AS target_properties
"""

ENTITY_NAME_LOOKUP = """
CALL db.index.fulltext.queryNodes('entity_fulltext_idx', $name)
YIELD node, score
WITH node, score
ORDER BY score DESC
LIMIT 1
RETURN
    node.aim_id AS aim_id,
    elementId(node) AS entity_id,
    labels(node) AS labels,
    node.name AS name,
    score
"""

ENTITY_NAME_LOOKUP_TENANT = """
CALL db.index.fulltext.queryNodes('entity_fulltext_idx', $name)
YIELD node, score
WITH node, score
WHERE node.tenant_id = $tenant_id
ORDER BY score DESC
LIMIT 1
RETURN
    node.aim_id AS aim_id,
    elementId(node) AS entity_id,
    labels(node) AS labels,
    node.name AS name,
    score
"""

# ── Vector search on the Neo4j entity_embedding_idx ───────────────────────────
# Activates the previously-dormant entity_embedding_idx. Unifies vector and
# fulltext retrieval into a single graph-aware query surface.
ENTITY_VECTOR_SEARCH = """
CALL db.index.vector.queryNodes('entity_embedding_idx', $limit, $embedding)
YIELD node, score
RETURN
    coalesce(node.aim_id, elementId(node)) AS entity_id,
    labels(node)             AS labels,
    properties(node)         AS properties,
    score                    AS score
"""

ENTITY_VECTOR_SEARCH_TENANT = """
CALL db.index.vector.queryNodes('entity_embedding_idx', $limit, $embedding)
YIELD node, score
WITH node, score
WHERE node.tenant_id = $tenant_id
RETURN
    coalesce(node.aim_id, elementId(node)) AS entity_id,
    labels(node)             AS labels,
    properties(node)         AS properties,
    score                    AS score
"""

# Hybrid search: union of fulltext entity matches AND vector-similar entities.
# Scores are normalized before the union (fulltext/5 to approximate [0,1]).
# Produces a topology-aware candidate set for graph expansion.
ENTITY_HYBRID_SEARCH = """
CALL {
    CALL db.index.fulltext.queryNodes('entity_fulltext_idx', $query)
    YIELD node, score
    WITH node, score
    ORDER BY score DESC
    LIMIT $limit
    RETURN node, (score / 5.0) AS score, 'fulltext' AS mode
    UNION
    CALL db.index.vector.queryNodes('entity_embedding_idx', $limit, $embedding)
    YIELD node, score
    RETURN node, score, 'vector' AS mode
}
WITH node, max(score) AS score
ORDER BY score DESC
LIMIT $limit
RETURN
    coalesce(node.aim_id, elementId(node)) AS entity_id,
    labels(node)             AS labels,
    properties(node)         AS properties,
    score                    AS score
"""

ENTITY_HYBRID_SEARCH_TENANT = """
CALL {
    CALL db.index.fulltext.queryNodes('entity_fulltext_idx', $query)
    YIELD node, score
    WITH node, score WHERE node.tenant_id = $tenant_id
    ORDER BY score DESC
    LIMIT $limit
    RETURN node, (score / 5.0) AS score
    UNION
    CALL db.index.vector.queryNodes('entity_embedding_idx', $limit, $embedding)
    YIELD node, score
    WITH node, score WHERE node.tenant_id = $tenant_id
    RETURN node, score
}
WITH node, max(score) AS score
ORDER BY score DESC
LIMIT $limit
RETURN
    coalesce(node.aim_id, elementId(node)) AS entity_id,
    labels(node)             AS labels,
    properties(node)         AS properties,
    score                    AS score
"""

FETCH_ENTITY_BY_ID = """
MATCH (n)
WHERE n.aim_id = $entity_id OR elementId(n) = $entity_id
RETURN
    coalesce(n.aim_id, elementId(n)) AS entity_id,
    labels(n)      AS labels,
    properties(n)  AS properties
LIMIT 1
"""

# ── Write ─────────────────────────────────────────────────────────────────────

UPSERT_ENTITY = """
MERGE (n {aim_id: $entity_id})
SET n += $properties
WITH n, $labels AS lbls
CALL apoc.create.addLabels(n, lbls) YIELD node
RETURN node
"""

# Tenant-scoped upsert: stamps tenant_id into every entity.
UPSERT_ENTITY_TENANT = """
MERGE (n {aim_id: $entity_id})
SET n += $properties
SET n.tenant_id = $tenant_id
WITH n, $labels AS lbls
CALL apoc.create.addLabels(n, lbls) YIELD node
RETURN node
"""

UPSERT_RELATIONSHIP = """
MATCH (a {aim_id: $source_id})
MATCH (b {aim_id: $target_id})
CALL apoc.merge.relationship(a, $rel_type, {}, $properties, b)
YIELD rel
RETURN rel
"""

DELETE_ENTITY = """
MATCH (n {aim_id: $entity_id})
DETACH DELETE n
"""

# ── Corpus snapshots (for live-ingestion cross-reference derivation) ─────────
#
# These are bounded reads that back ``Neo4jClient.list_entity_snapshot`` and
# ``list_relationship_snapshot``. The ingest worker calls them once per
# extraction job to union the existing corpus with the newly-extracted batch
# before running ``derive_mentions`` — so a Slack message that names an
# already-ingested Jira ticket gets the MENTIONS edge it deserves, not a
# leaf-node miss.
#
# The ``LIMIT`` is set at call-site (default 10000); tune via
# ``ingestion_cross_corpus_snapshot_limit`` if the corpus grows beyond that.
LIST_ENTITY_SNAPSHOT = """
MATCH (n)
WHERE n.aim_id IS NOT NULL
  AND ($tenant_id = "" OR n.tenant_id = $tenant_id)
RETURN
    n.aim_id      AS entity_id,
    labels(n)     AS labels,
    properties(n) AS properties
LIMIT $limit
"""

LIST_RELATIONSHIP_SNAPSHOT = """
MATCH (a)-[r]->(b)
WHERE a.aim_id IS NOT NULL AND b.aim_id IS NOT NULL
  AND ($tenant_id = "" OR (a.tenant_id = $tenant_id AND b.tenant_id = $tenant_id))
RETURN
    a.aim_id  AS source_id,
    b.aim_id  AS target_id,
    type(r)   AS rel_type
LIMIT $limit
"""

# ── Path finding (multi-hop reasoning) ───────────────────────────────────────

SHORTEST_PATH_QUERY = """
MATCH (a {aim_id: $source_aim_id}), (b {aim_id: $target_aim_id})
MATCH path = shortestPath((a)-[*..10]-(b))
WHERE $tenant_id = "" OR all(n IN nodes(path) WHERE n.tenant_id = $tenant_id)
RETURN
    [n IN nodes(path) | {
        entity_id: coalesce(n.aim_id, elementId(n)),
        aim_id: n.aim_id,
        labels: labels(n),
        name: n.name
    }] AS path_nodes,
    [r IN relationships(path) | {
        rel_id: elementId(r),
        rel_type: type(r),
        source_id: coalesce(startNode(r).aim_id, elementId(startNode(r))),
        target_id: coalesce(endNode(r).aim_id, elementId(endNode(r))),
        properties: properties(r)
    }] AS path_rels,
    length(path) AS hops
LIMIT 1
"""

ALL_SHORTEST_PATHS_QUERY = """
MATCH (a {aim_id: $source_aim_id}), (b {aim_id: $target_aim_id})
MATCH path = allShortestPaths((a)-[*..10]-(b))
WHERE $tenant_id = "" OR all(n IN nodes(path) WHERE n.tenant_id = $tenant_id)
RETURN
    [n IN nodes(path) | {
        entity_id: coalesce(n.aim_id, elementId(n)),
        aim_id: n.aim_id,
        labels: labels(n),
        name: n.name
    }] AS path_nodes,
    [r IN relationships(path) | {
        rel_id: elementId(r),
        rel_type: type(r),
        source_id: coalesce(startNode(r).aim_id, elementId(startNode(r))),
        target_id: coalesce(endNode(r).aim_id, elementId(endNode(r))),
        properties: properties(r)
    }] AS path_rels,
    length(path) AS hops
LIMIT 5
"""

# ── Index management (run once at startup) ────────────────────────────────────

CREATE_FULLTEXT_INDEX = """
CREATE FULLTEXT INDEX entity_fulltext_idx IF NOT EXISTS
FOR (n:Entity)
ON EACH [n.name, n.description, n.title, n.content]
OPTIONS { indexConfig: { `fulltext.analyzer`: 'english' } }
"""

CREATE_VECTOR_INDEX = """
CREATE VECTOR INDEX entity_embedding_idx IF NOT EXISTS
FOR (n:Entity) ON (n.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 1536,
        `vector.similarity_function`: 'cosine'
    }
}
"""
