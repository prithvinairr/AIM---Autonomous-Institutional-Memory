/**
 * Barnes-Hut octree repulsion for 3D force-directed graphs.
 *
 * The naïve n-body loop is O(n²) per iteration; with ~1500 seed nodes the
 * nebula stalls. Barnes-Hut recursively partitions space into octants and,
 * when a node's view of a subtree satisfies `size / distance < θ`, treats
 * the whole subtree as a single center of mass. That drops the per-
 * iteration cost to O(n log n) for the common case of reasonably uniform
 * point clouds.
 *
 * Contract pinned by `__tests__/barnes-hut.test.ts`:
 *   - θ=0 reproduces exact pairwise forces (no approximation).
 *   - θ=0.5 matches pairwise within 10% per-node magnitude error.
 *   - Empty and singleton inputs do not throw.
 *   - Co-located nodes never produce NaN/Infinity.
 */

export type Vec3 = [number, number, number];

const EPS = 1e-6;

// ── Exact pairwise oracle ────────────────────────────────────────────────────

/**
 * Exact pairwise repulsion — the reference implementation. Used both as the
 * test oracle and as the direct path when `theta <= 0`.
 */
export function computeRepulsionPairwise(
  positions: ReadonlyArray<Vec3>,
  strength: number,
): Vec3[] {
  const n = positions.length;
  const out: Vec3[] = Array.from({ length: n }, () => [0, 0, 0]);
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const dx = positions[j][0] - positions[i][0];
      const dy = positions[j][1] - positions[i][1];
      const dz = positions[j][2] - positions[i][2];
      const distSq = dx * dx + dy * dy + dz * dz;
      if (distSq < EPS * EPS) continue;
      const dist = Math.sqrt(distSq);
      const force = strength / distSq;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      const fz = (dz / dist) * force;
      // i receives -force (pushed away from j when strength < 0); j receives +force.
      out[i][0] -= fx;
      out[i][1] -= fy;
      out[i][2] -= fz;
      out[j][0] += fx;
      out[j][1] += fy;
      out[j][2] += fz;
    }
  }
  return out;
}

// ── Octree ───────────────────────────────────────────────────────────────────

interface OctNode {
  // AABB center + half-size (side length / 2).
  cx: number;
  cy: number;
  cz: number;
  half: number;
  // Aggregate: total mass (node count) and center-of-mass weighted sum.
  mass: number;
  comX: number;
  comY: number;
  comZ: number;
  // Either a leaf (single index) or internal (8 children, some undefined).
  index: number;
  children: (OctNode | undefined)[] | null;
}

function makeNode(cx: number, cy: number, cz: number, half: number): OctNode {
  return {
    cx,
    cy,
    cz,
    half,
    mass: 0,
    comX: 0,
    comY: 0,
    comZ: 0,
    index: -1,
    children: null,
  };
}

function octant(node: OctNode, x: number, y: number, z: number): number {
  return (
    (x >= node.cx ? 1 : 0) |
    (y >= node.cy ? 2 : 0) |
    (z >= node.cz ? 4 : 0)
  );
}

function childBox(node: OctNode, oct: number): { cx: number; cy: number; cz: number; half: number } {
  const h = node.half / 2;
  return {
    cx: node.cx + (oct & 1 ? h : -h),
    cy: node.cy + (oct & 2 ? h : -h),
    cz: node.cz + (oct & 4 ? h : -h),
    half: h,
  };
}

function insert(
  node: OctNode,
  positions: ReadonlyArray<Vec3>,
  idx: number,
  depth: number,
): void {
  // Depth cap: co-located points would recurse forever. At the cap we just
  // fold the extra mass into the existing leaf's COM accumulator.
  const MAX_DEPTH = 32;

  if (node.mass === 0) {
    node.index = idx;
    node.mass = 1;
    node.comX = positions[idx][0];
    node.comY = positions[idx][1];
    node.comZ = positions[idx][2];
    return;
  }

  // Accumulate COM on the way down — every traversed node sees this point.
  node.comX += positions[idx][0];
  node.comY += positions[idx][1];
  node.comZ += positions[idx][2];
  node.mass += 1;

  if (depth >= MAX_DEPTH) return;

  if (node.children === null) {
    // Leaf → split. Re-insert the existing point, then insert the new one.
    node.children = [undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined];
    const oldIdx = node.index;
    node.index = -1;
    const oldOct = octant(node, positions[oldIdx][0], positions[oldIdx][1], positions[oldIdx][2]);
    const box = childBox(node, oldOct);
    const child = makeNode(box.cx, box.cy, box.cz, box.half);
    node.children[oldOct] = child;
    insert(child, positions, oldIdx, depth + 1);
  }

  const oct = octant(node, positions[idx][0], positions[idx][1], positions[idx][2]);
  if (!node.children[oct]) {
    const box = childBox(node, oct);
    node.children[oct] = makeNode(box.cx, box.cy, box.cz, box.half);
  }
  insert(node.children[oct]!, positions, idx, depth + 1);
}

function computeForceOn(
  target: number,
  node: OctNode,
  positions: ReadonlyArray<Vec3>,
  theta: number,
  strength: number,
  out: Vec3,
): void {
  if (node.mass === 0) return;

  const px = positions[target][0];
  const py = positions[target][1];
  const pz = positions[target][2];

  // Leaf holding only the target itself — skip (no self-force).
  if (node.children === null && node.index === target) return;

  const comX = node.comX / node.mass;
  const comY = node.comY / node.mass;
  const comZ = node.comZ / node.mass;

  const dx = comX - px;
  const dy = comY - py;
  const dz = comZ - pz;
  const distSq = dx * dx + dy * dy + dz * dz;

  const size = node.half * 2;

  const isLeaf = node.children === null;
  // Approximation criterion — or always recurse when θ=0.
  const canApproximate = theta > 0 && isLeaf === false && size * size < theta * theta * distSq;

  if (isLeaf || canApproximate) {
    if (distSq < EPS * EPS) return;
    const dist = Math.sqrt(distSq);
    // Force on target from aggregate of mass `node.mass` at COM.
    // Sign: target is pushed away from the mass when strength < 0.
    const force = (strength * node.mass) / distSq;
    out[0] -= (dx / dist) * force;
    out[1] -= (dy / dist) * force;
    out[2] -= (dz / dist) * force;
    return;
  }

  if (node.children) {
    for (const child of node.children) {
      if (child) computeForceOn(target, child, positions, theta, strength, out);
    }
  }
}

// ── Public entry point ──────────────────────────────────────────────────────

/**
 * Per-node repulsion forces using Barnes-Hut approximation.
 *
 * @param positions - N points in 3D. Not mutated.
 * @param strength  - Per-pair force scalar. Negative = repulsion (matches
 *                    the existing `compute3DLayout` convention).
 * @param theta     - Barnes-Hut opening angle. 0 = exact pairwise,
 *                    higher = more approximation. Typical: 0.5.
 * @returns N force vectors aligned with `positions`.
 */
export function computeRepulsion(
  positions: ReadonlyArray<Vec3>,
  strength: number,
  theta: number,
): Vec3[] {
  const n = positions.length;
  if (n === 0) return [];
  if (n === 1) return [[0, 0, 0]];

  // θ=0 → exact pairwise. No tree needed and cheaper for small n anyway.
  if (theta <= 0) return computeRepulsionPairwise(positions, strength);

  // Bounding box.
  let minX = positions[0][0], maxX = positions[0][0];
  let minY = positions[0][1], maxY = positions[0][1];
  let minZ = positions[0][2], maxZ = positions[0][2];
  for (let i = 1; i < n; i++) {
    const p = positions[i];
    if (p[0] < minX) minX = p[0]; else if (p[0] > maxX) maxX = p[0];
    if (p[1] < minY) minY = p[1]; else if (p[1] > maxY) maxY = p[1];
    if (p[2] < minZ) minZ = p[2]; else if (p[2] > maxZ) maxZ = p[2];
  }
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const cz = (minZ + maxZ) / 2;
  // Pad so boundary points fall strictly inside the root box.
  const half = Math.max(maxX - minX, maxY - minY, maxZ - minZ) / 2 + 1e-3;

  const root = makeNode(cx, cy, cz, half);
  for (let i = 0; i < n; i++) insert(root, positions, i, 0);

  const out: Vec3[] = Array.from({ length: n }, () => [0, 0, 0]);
  for (let i = 0; i < n; i++) {
    computeForceOn(i, root, positions, theta, strength, out[i]);
  }
  return out;
}
