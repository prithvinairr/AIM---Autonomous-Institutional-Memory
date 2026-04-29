/**
 * Phase 2 — Causal Lineage on the frontend.
 *
 * The 3D nebula must:
 *   (a) consume authoritative `graph_edges` (directed) when present,
 *   (b) preserve direction under dedup so A→B and B→A stay distinct,
 *   (c) map edge confidence to a bounded opacity in [0.08, 0.30].
 *
 * These helpers mirror the logic in `knowledge-graph.tsx`. Duplicating
 * them here keeps the test isolated from React/Three imports while
 * pinning the exact contract the component implements.
 */
import { describe, it, expect } from "vitest";

interface Edge {
  source_entity_id: string;
  target_entity_id: string;
  rel_type: string;
  confidence?: number;
}

interface Link {
  sourceId: string;
  targetId: string;
  type: string;
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
    });
  }
  return links;
}

function opacityFor(confidence: number | undefined): number {
  const c = typeof confidence === "number" ? confidence : 1;
  return 0.08 + Math.max(0, Math.min(1, c)) * 0.22;
}

describe("Phase 2 — graph_edges ingestion", () => {
  it("preserves direction: A→B and B→A are distinct links", () => {
    const links = buildLinks(
      ["a", "b"],
      [
        { source_entity_id: "a", target_entity_id: "b", rel_type: "DEPENDS_ON" },
        { source_entity_id: "b", target_entity_id: "a", rel_type: "DEPENDS_ON" },
      ],
    );
    expect(links).toHaveLength(2);
    expect(links[0]).toMatchObject({ sourceId: "a", targetId: "b" });
    expect(links[1]).toMatchObject({ sourceId: "b", targetId: "a" });
  });

  it("dedups identical directed edges of the same type", () => {
    const links = buildLinks(
      ["a", "b"],
      [
        { source_entity_id: "a", target_entity_id: "b", rel_type: "DEPENDS_ON" },
        { source_entity_id: "a", target_entity_id: "b", rel_type: "DEPENDS_ON" },
      ],
    );
    expect(links).toHaveLength(1);
  });

  it("keeps same-direction edges of different types as separate links", () => {
    const links = buildLinks(
      ["a", "b"],
      [
        { source_entity_id: "a", target_entity_id: "b", rel_type: "DEPENDS_ON" },
        { source_entity_id: "a", target_entity_id: "b", rel_type: "OWNS" },
      ],
    );
    expect(links).toHaveLength(2);
    expect(links.map((l) => l.type).sort()).toEqual(["DEPENDS_ON", "OWNS"]);
  });

  it("drops edges referencing unknown nodes", () => {
    const links = buildLinks(
      ["a", "b"],
      [
        { source_entity_id: "a", target_entity_id: "c", rel_type: "OWNS" },
        { source_entity_id: "x", target_entity_id: "b", rel_type: "OWNS" },
      ],
    );
    expect(links).toHaveLength(0);
  });

  it("defaults confidence to 1 when the backend omits it", () => {
    const links = buildLinks(
      ["a", "b"],
      [{ source_entity_id: "a", target_entity_id: "b", rel_type: "LINKS_TO" }],
    );
    expect(links[0].confidence).toBe(1);
  });
});

describe("Phase 2 — confidence → opacity", () => {
  it("maps confidence=0 to the floor (0.08)", () => {
    expect(opacityFor(0)).toBeCloseTo(0.08, 5);
  });

  it("maps confidence=1 to the ceiling (0.30)", () => {
    expect(opacityFor(1)).toBeCloseTo(0.3, 5);
  });

  it("interpolates linearly mid-range", () => {
    expect(opacityFor(0.5)).toBeCloseTo(0.19, 5);
  });

  it("clamps out-of-range values without throwing", () => {
    expect(opacityFor(-1)).toBeCloseTo(0.08, 5);
    expect(opacityFor(10)).toBeCloseTo(0.3, 5);
  });

  it("treats undefined confidence as 1 (trust the edge)", () => {
    expect(opacityFor(undefined)).toBeCloseTo(0.3, 5);
  });
});
