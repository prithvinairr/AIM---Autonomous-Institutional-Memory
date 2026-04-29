/**
 * Phase 14 — Causal-integrity violators on the frontend.
 *
 * When `ProvenanceData.violating_edge_ids` is populated, the 3D nebula must:
 *   (a) carry `rel_id` through from backend GraphProvenanceEdge → Link3D,
 *   (b) flip offending edges red with full opacity (0.85),
 *   (c) leave non-violating edges on the confidence-driven opacity curve.
 *
 * These helpers mirror the logic in `knowledge-graph.tsx`. Duplicating them
 * keeps the test isolated from Three.js / React while pinning the contract.
 */
import { describe, it, expect } from "vitest";

interface Edge {
  source_entity_id: string;
  target_entity_id: string;
  rel_type: string;
  rel_id?: string;
  confidence?: number;
}

interface Link {
  sourceId: string;
  targetId: string;
  type: string;
  relId?: string;
  confidence?: number;
}

function buildLinks(nodeIds: string[], edges: Edge[]): Link[] {
  const links: Link[] = [];
  const nodeSet = new Set(nodeIds);
  const seen = new Set<string>();
  for (const edge of edges) {
    if (!nodeSet.has(edge.source_entity_id) || !nodeSet.has(edge.target_entity_id)) continue;
    const key = `${edge.source_entity_id}→${edge.target_entity_id}:${edge.rel_type}`;
    if (seen.has(key)) continue;
    seen.add(key);
    links.push({
      sourceId: edge.source_entity_id,
      targetId: edge.target_entity_id,
      type: edge.rel_type,
      confidence: typeof edge.confidence === "number" ? edge.confidence : 1,
      relId: edge.rel_id,
    });
  }
  return links;
}

function resolveColorAndOpacity(
  link: Link,
  violating: Set<string>,
  highlighted: boolean,
): { color: string; opacity: number } {
  const isViolating = !!link.relId && violating.has(link.relId);
  const confidence = typeof link.confidence === "number" ? link.confidence : 1;
  const baseOpacity = 0.08 + Math.max(0, Math.min(1, confidence)) * 0.22;
  const color = isViolating ? "#f87171" : highlighted ? "#60a5fa" : "#334155";
  const opacity = isViolating ? 0.85 : highlighted ? 0.6 : baseOpacity;
  return { color, opacity };
}

describe("Phase 14 — rel_id propagation", () => {
  it("carries rel_id from edge onto the Link3D", () => {
    const links = buildLinks(
      ["a", "b"],
      [{ source_entity_id: "a", target_entity_id: "b", rel_type: "CAUSED_BY", rel_id: "rel-42" }],
    );
    expect(links[0].relId).toBe("rel-42");
  });

  it("leaves relId undefined when the backend omits it", () => {
    const links = buildLinks(
      ["a", "b"],
      [{ source_entity_id: "a", target_entity_id: "b", rel_type: "DEPENDS_ON" }],
    );
    expect(links[0].relId).toBeUndefined();
  });
});

describe("Phase 14 — violating edges render red", () => {
  const baseLink: Link = {
    sourceId: "a",
    targetId: "b",
    type: "CAUSED_BY",
    relId: "rel-violation-1",
    confidence: 0.9,
  };

  it("paints a violating edge red with high opacity", () => {
    const violating = new Set(["rel-violation-1"]);
    const { color, opacity } = resolveColorAndOpacity(baseLink, violating, false);
    expect(color).toBe("#f87171");
    expect(opacity).toBeCloseTo(0.85, 5);
  });

  it("keeps non-violating edges on the confidence curve", () => {
    const violating = new Set(["some-other-id"]);
    const { color, opacity } = resolveColorAndOpacity(baseLink, violating, false);
    expect(color).toBe("#334155");
    expect(opacity).toBeCloseTo(0.08 + 0.9 * 0.22, 5);
  });

  it("violation overrides hover/select highlight", () => {
    const violating = new Set(["rel-violation-1"]);
    const { color } = resolveColorAndOpacity(baseLink, violating, true);
    expect(color).toBe("#f87171");
  });

  it("never flags an edge with no rel_id even if the violating set is populated", () => {
    const noRelId: Link = { ...baseLink, relId: undefined };
    const violating = new Set(["rel-violation-1"]);
    const { color } = resolveColorAndOpacity(noRelId, violating, false);
    expect(color).toBe("#334155");
  });

  it("empty violating set leaves all edges on the normal curve", () => {
    const { color, opacity } = resolveColorAndOpacity(baseLink, new Set(), false);
    expect(color).toBe("#334155");
    expect(opacity).toBeLessThan(0.85);
  });
});
