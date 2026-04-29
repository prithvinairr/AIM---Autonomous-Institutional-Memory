/**
 * Tests for the 3D force layout algorithm used in the Knowledge Nebula.
 */
import { describe, it, expect } from "vitest";

// ── Recreate minimal types for testing ──────────────────────────────────────

interface Node3D {
  id: string;
  position: [number, number, number];
}

interface Link3D {
  sourceId: string;
  targetId: string;
}

// Inline the layout algorithm for testing
function compute3DLayout(
  nodes: Node3D[],
  links: Link3D[],
  iterations: number = 60,
): void {
  // Force convention matches lib/barnes-hut.ts computeRepulsion: positive
  // strength → repulsive (i pushed away from j). The test previously had -2.0
  // which inverted the force into attractive clustering, collapsing nodes
  // onto each other and breaking the linked-vs-unlinked and convergence
  // assertions below.
  const REPULSION = 2.0;
  const LINK_DISTANCE = 3.5;
  const LINK_STRENGTH = 0.15;
  const CENTER_STRENGTH = 0.03;
  const DAMPING = 0.85;

  const n = nodes.length || 1;
  const golden = (1 + Math.sqrt(5)) / 2;
  nodes.forEach((node, i) => {
    const theta = Math.acos(1 - (2 * (i + 0.5)) / n);
    const phi = 2 * Math.PI * i / golden;
    const r = 4;
    node.position = [
      r * Math.sin(theta) * Math.cos(phi),
      r * Math.sin(theta) * Math.sin(phi),
      r * Math.cos(theta),
    ];
  });

  const velocities = nodes.map(() => [0, 0, 0] as [number, number, number]);
  const nodeMap = new Map(nodes.map((n, i) => [n.id, i]));

  for (let iter = 0; iter < iterations; iter++) {
    const alpha = 1 - iter / iterations;

    for (let i = 0; i < nodes.length; i++) {
      for (let d = 0; d < 3; d++) {
        velocities[i][d] -= nodes[i].position[d] * CENTER_STRENGTH * alpha;
      }
    }

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[j].position[0] - nodes[i].position[0];
        const dy = nodes[j].position[1] - nodes[i].position[1];
        const dz = nodes[j].position[2] - nodes[i].position[2];
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.1;
        const force = (REPULSION * alpha) / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        const fz = (dz / dist) * force;
        velocities[i][0] -= fx;
        velocities[i][1] -= fy;
        velocities[i][2] -= fz;
        velocities[j][0] += fx;
        velocities[j][1] += fy;
        velocities[j][2] += fz;
      }
    }

    for (const link of links) {
      const si = nodeMap.get(link.sourceId);
      const ti = nodeMap.get(link.targetId);
      if (si === undefined || ti === undefined) continue;
      const dx = nodes[ti].position[0] - nodes[si].position[0];
      const dy = nodes[ti].position[1] - nodes[si].position[1];
      const dz = nodes[ti].position[2] - nodes[si].position[2];
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.1;
      const displacement = (dist - LINK_DISTANCE) * LINK_STRENGTH * alpha;
      velocities[si][0] += (dx / dist) * displacement;
      velocities[si][1] += (dy / dist) * displacement;
      velocities[si][2] += (dz / dist) * displacement;
      velocities[ti][0] -= (dx / dist) * displacement;
      velocities[ti][1] -= (dy / dist) * displacement;
      velocities[ti][2] -= (dz / dist) * displacement;
    }

    for (let i = 0; i < nodes.length; i++) {
      for (let d = 0; d < 3; d++) {
        velocities[i][d] *= DAMPING;
        nodes[i].position[d] += velocities[i][d];
      }
    }
  }
}

describe("3D Force Layout", () => {
  it("positions nodes at distinct locations", () => {
    const nodes: Node3D[] = [
      { id: "a", position: [0, 0, 0] },
      { id: "b", position: [0, 0, 0] },
      { id: "c", position: [0, 0, 0] },
    ];
    compute3DLayout(nodes, []);

    // All nodes should be at different positions
    const positions = nodes.map((n) => n.position.join(","));
    const unique = new Set(positions);
    expect(unique.size).toBe(3);
  });

  it("linked nodes are closer than unlinked nodes", () => {
    const nodes: Node3D[] = [
      { id: "a", position: [0, 0, 0] },
      { id: "b", position: [0, 0, 0] },
      { id: "c", position: [0, 0, 0] },
    ];
    const links: Link3D[] = [{ sourceId: "a", targetId: "b" }];
    compute3DLayout(nodes, links, 120);

    const dist = (a: Node3D, b: Node3D) =>
      Math.sqrt(
        (a.position[0] - b.position[0]) ** 2 +
        (a.position[1] - b.position[1]) ** 2 +
        (a.position[2] - b.position[2]) ** 2,
      );

    const linked = dist(nodes[0], nodes[1]);
    const unlinked = dist(nodes[0], nodes[2]);
    expect(linked).toBeLessThan(unlinked);
  });

  it("all positions use 3 dimensions (z != 0)", () => {
    const nodes: Node3D[] = Array.from({ length: 5 }, (_, i) => ({
      id: `n${i}`,
      position: [0, 0, 0] as [number, number, number],
    }));
    compute3DLayout(nodes, []);

    const hasZ = nodes.some((n) => Math.abs(n.position[2]) > 0.01);
    expect(hasZ).toBe(true);
  });

  it("handles single node without error", () => {
    const nodes: Node3D[] = [{ id: "solo", position: [0, 0, 0] }];
    expect(() => compute3DLayout(nodes, [])).not.toThrow();
  });

  it("handles empty graph", () => {
    expect(() => compute3DLayout([], [])).not.toThrow();
  });

  it("nodes converge near center after simulation", () => {
    const nodes: Node3D[] = Array.from({ length: 4 }, (_, i) => ({
      id: `n${i}`,
      position: [0, 0, 0] as [number, number, number],
    }));
    compute3DLayout(nodes, [], 200);

    // All nodes should be within a reasonable radius from center
    for (const n of nodes) {
      const dist = Math.sqrt(
        n.position[0] ** 2 + n.position[1] ** 2 + n.position[2] ** 2,
      );
      expect(dist).toBeLessThan(20);
    }
  });
});
