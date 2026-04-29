import { describe, expect, it } from "vitest";
import { buildProvenanceNebulaMap, edgeColorFor } from "@/lib/provenance-map";
import type { ProvenanceData } from "@/types/aim";

const baseProvenance: ProvenanceData = {
  overall_confidence: 0.91,
  citation_spans: [],
  resolved_entities: [],
  temporal_chain: [],
  sub_query_traces: [
    {
      sub_query_id: "sq-1",
      sub_query_text: "What caused the treatment change?",
      source_ids: ["src-1"],
      graph_node_ids: ["patient-1", "study-1"],
    },
  ],
  reasoning_steps: [],
  graph_nodes: [
    {
      entity_id: "patient-1",
      entity_type: "Patient",
      labels: ["Entity", "Patient"],
      properties: { name: "Patient A" },
      relationship_path: [],
    },
    {
      entity_id: "study-1",
      entity_type: "Study",
      labels: ["Entity", "Study"],
      properties: { title: "RENAL-AI Study" },
      relationship_path: [],
    },
    {
      entity_id: "treatment-1",
      entity_type: "Treatment",
      labels: ["Entity", "Treatment"],
      properties: { name: "SGLT2 protocol" },
      relationship_path: [],
    },
    {
      entity_id: "noise-1",
      entity_type: "Document",
      labels: ["Entity", "Document"],
      properties: { name: "Uncited cafeteria policy" },
      relationship_path: [],
    },
  ],
  graph_edges: [
    {
      source_entity_id: "patient-1",
      target_entity_id: "study-1",
      rel_type: "ENROLLED_IN",
      confidence: 0.82,
      rel_id: "rel-1",
    },
    {
      source_entity_id: "study-1",
      target_entity_id: "treatment-1",
      rel_type: "CAUSED_BY",
      confidence: 0.76,
      rel_id: "rel-2",
    },
    {
      source_entity_id: "noise-1",
      target_entity_id: "patient-1",
      rel_type: "MENTIONS",
      confidence: 1,
    },
  ],
};

describe("provenance nebula map", () => {
  it("keeps cited graph nodes plus one-hop evidence neighbors", () => {
    const map = buildProvenanceNebulaMap(baseProvenance);
    expect(map.nodes.map((node) => node.id).sort()).toEqual([
      "patient-1",
      "study-1",
      "treatment-1",
    ]);
    expect(map.nodes.find((node) => node.id === "patient-1")?.isCited).toBe(true);
    expect(map.nodes.find((node) => node.id === "treatment-1")?.isCited).toBe(false);
  });

  it("colors causal and supersession edges for visual lineage", () => {
    expect(edgeColorFor("CAUSED_BY")).toBe("#f97316");
    expect(edgeColorFor("SUPERSEDES")).toBe("#a78bfa");
    expect(edgeColorFor("UNKNOWN_REL")).toBe("#475569");
  });

  it("preserves authoritative edge confidence and rel_id", () => {
    const map = buildProvenanceNebulaMap(baseProvenance);
    expect(map.edges).toContainEqual({
      sourceId: "study-1",
      targetId: "treatment-1",
      type: "CAUSED_BY",
      color: "#f97316",
      confidence: 0.76,
      relId: "rel-2",
    });
  });
});
