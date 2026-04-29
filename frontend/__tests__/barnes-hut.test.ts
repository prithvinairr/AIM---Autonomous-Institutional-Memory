/**
 * Phase 8 — Barnes-Hut octree repulsion for the 3D knowledge nebula.
 *
 * The naïve force layout does pairwise repulsion in O(n²), so 1500-node
 * graphs (adversarial-seed scale) stall the UI. Barnes-Hut approximates
 * distant clusters as a single center of mass, bringing the per-iteration
 * cost down to O(n log n).
 *
 * These tests pin the contract the implementation must honour:
 *   (a) for θ=0 it degrades to exact pairwise (no approximation),
 *   (b) for θ=0.5 it matches pairwise within a small tolerance,
 *   (c) the net repulsion force on a centered node in a symmetric cloud
 *       stays near zero (no numerical drift baked in),
 *   (d) it handles empty and singleton inputs without throwing.
 *
 * The pairwise oracle lives in this file — the same formula the current
 * `compute3DLayout` loop uses, so drop-in parity is measurable.
 */
import { describe, it, expect } from "vitest";
import { computeRepulsion, computeRepulsionPairwise } from "../lib/barnes-hut";

type Vec3 = [number, number, number];

function randomCloud(n: number, seed: number): Vec3[] {
  // Mulberry32 — deterministic per-seed so tests are reproducible.
  let s = seed >>> 0;
  const rand = () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const out: Vec3[] = [];
  for (let i = 0; i < n; i++) {
    out.push([
      (rand() - 0.5) * 10,
      (rand() - 0.5) * 10,
      (rand() - 0.5) * 10,
    ]);
  }
  return out;
}

function maxAbsDelta(a: Vec3[], b: Vec3[]): number {
  let m = 0;
  for (let i = 0; i < a.length; i++) {
    for (let d = 0; d < 3; d++) {
      m = Math.max(m, Math.abs(a[i][d] - b[i][d]));
    }
  }
  return m;
}

function magnitude(v: Vec3): number {
  return Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

describe("Phase 8 — Barnes-Hut matches pairwise oracle", () => {
  it("θ=0 reproduces exact pairwise forces", () => {
    const positions = randomCloud(40, 1);
    const oracle = computeRepulsionPairwise(positions, -2.0);
    const bh = computeRepulsion(positions, -2.0, 0);
    expect(maxAbsDelta(oracle, bh)).toBeLessThan(1e-9);
  });

  it("θ=0.5 stays within 10% of pairwise on 200-node cloud", () => {
    const positions = randomCloud(200, 2);
    const oracle = computeRepulsionPairwise(positions, -2.0);
    const bh = computeRepulsion(positions, -2.0, 0.5);
    // Compare per-node force magnitudes: the angle between vectors also
    // matters but magnitude error is the bound that drives visual drift.
    let maxRelErr = 0;
    for (let i = 0; i < positions.length; i++) {
      const oMag = magnitude(oracle[i]);
      const bMag = magnitude(bh[i]);
      if (oMag < 1e-6) continue;
      maxRelErr = Math.max(maxRelErr, Math.abs(oMag - bMag) / oMag);
    }
    expect(maxRelErr).toBeLessThan(0.1);
  });

  it("force on a node at the center of a symmetric cloud is ~zero", () => {
    const positions: Vec3[] = [
      [0, 0, 0],
      [1, 0, 0],
      [-1, 0, 0],
      [0, 1, 0],
      [0, -1, 0],
      [0, 0, 1],
      [0, 0, -1],
    ];
    const bh = computeRepulsion(positions, -2.0, 0.5);
    expect(magnitude(bh[0])).toBeLessThan(1e-9);
  });
});

describe("Phase 8 — edge cases", () => {
  it("empty input returns empty output", () => {
    expect(computeRepulsion([], -2.0, 0.5)).toEqual([]);
  });

  it("single node has no force", () => {
    const out = computeRepulsion([[0, 0, 0]], -2.0, 0.5);
    expect(out).toEqual([[0, 0, 0]]);
  });

  it("co-located nodes do not divide by zero", () => {
    const positions: Vec3[] = [
      [0, 0, 0],
      [0, 0, 0],
    ];
    const out = computeRepulsion(positions, -2.0, 0.5);
    // Either finite or zero — never NaN/Infinity.
    for (const v of out) {
      for (const d of v) expect(Number.isFinite(d)).toBe(true);
    }
  });
});
