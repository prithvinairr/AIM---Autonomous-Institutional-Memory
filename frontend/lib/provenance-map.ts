import type { GraphNode, GraphProvenanceEdge, ProvenanceData } from "@/types/aim";

export interface ProvenanceNebulaNode {
  id: string;
  label: string;
  type: string;
  labels: string[];
  properties: Record<string, unknown>;
  isCited: boolean;
}

export interface ProvenanceNebulaEdge {
  sourceId: string;
  targetId: string;
  type: string;
  confidence: number;
  relId?: string;
  color: string;
}

export interface ProvenanceNebulaMap {
  nodes: ProvenanceNebulaNode[];
  edges: ProvenanceNebulaEdge[];
  citedEntityIds: Set<string>;
}

const EDGE_COLORS: Record<string, string> = {
  CAUSED_BY: "#f97316",
  LED_TO: "#fb7185",
  SUPERSEDES: "#a78bfa",
  APPROVED_BY: "#22c55e",
  PROPOSED_BY: "#38bdf8",
  OWNS: "#60a5fa",
  DEPENDS_ON: "#2dd4bf",
  EVIDENCES: "#facc15",
  SUPPORTED_BY: "#facc15",
  CONTRADICTS: "#ef4444",
};

export function edgeColorFor(relType: string): string {
  return EDGE_COLORS[relType] ?? "#475569";
}

function labelForNode(node: GraphNode): string {
  const props = node.properties ?? {};
  return (
    String(props.name ?? props.title ?? props.canonical_name ?? "") ||
    node.entity_type ||
    node.entity_id.slice(0, 8)
  );
}

function citedEntityIdsFrom(provenance: ProvenanceData): Set<string> {
  const cited = new Set<string>();

  for (const trace of provenance.sub_query_traces ?? []) {
    for (const id of trace.graph_node_ids ?? []) cited.add(id);
  }

  for (const fact of provenance.institutional_facts ?? []) {
    if (fact.subject_entity_id) cited.add(fact.subject_entity_id);
    if (fact.object_entity_id) cited.add(fact.object_entity_id);
  }

  return cited;
}

function shouldKeepNode(
  node: GraphNode,
  cited: Set<string>,
  edges: GraphProvenanceEdge[] | undefined,
): boolean {
  if (cited.size === 0) return true;
  if (cited.has(node.entity_id)) return true;
  return (edges ?? []).some(
    (edge) => cited.has(edge.source_entity_id) && edge.target_entity_id === node.entity_id,
  );
}

export function buildProvenanceNebulaMap(
  provenance: ProvenanceData | null | undefined,
): ProvenanceNebulaMap {
  if (!provenance?.graph_nodes?.length) {
    return { nodes: [], edges: [], citedEntityIds: new Set() };
  }

  const citedEntityIds = citedEntityIdsFrom(provenance);
  const sourceNodes = provenance.graph_nodes.filter((node) =>
    shouldKeepNode(node, citedEntityIds, provenance.graph_edges),
  );
  const nodes = sourceNodes.map((node) => ({
    id: node.entity_id,
    label: labelForNode(node),
    type: node.entity_type,
    labels: node.labels,
    properties: node.properties,
    isCited: citedEntityIds.size === 0 || citedEntityIds.has(node.entity_id),
  }));

  const nodeIds = new Set(nodes.map((node) => node.id));
  const seen = new Set<string>();
  const edges: ProvenanceNebulaEdge[] = [];

  if (provenance.graph_edges?.length) {
    for (const edge of provenance.graph_edges) {
      if (!nodeIds.has(edge.source_entity_id) || !nodeIds.has(edge.target_entity_id)) {
        continue;
      }
      const key = [
        edge.source_entity_id,
        edge.target_entity_id,
        edge.rel_type,
        edge.rel_id ?? "",
      ].join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({
        sourceId: edge.source_entity_id,
        targetId: edge.target_entity_id,
        type: edge.rel_type,
        confidence: typeof edge.confidence === "number" ? edge.confidence : 1,
        relId: edge.rel_id,
        color: edgeColorFor(edge.rel_type),
      });
    }
  } else {
    for (const node of provenance.graph_nodes) {
      if (!nodeIds.has(node.entity_id)) continue;
      for (const pathItem of node.relationship_path ?? []) {
        const [relType, ...rest] = pathItem.split(":");
        const targetId = rest.join(":");
        if (!relType || !nodeIds.has(targetId)) continue;
        const key = [node.entity_id, targetId, relType].join("|");
        if (seen.has(key)) continue;
        seen.add(key);
        edges.push({
          sourceId: node.entity_id,
          targetId,
          type: relType,
          confidence: 1,
          color: edgeColorFor(relType),
        });
      }
    }
  }

  return { nodes, edges, citedEntityIds };
}
