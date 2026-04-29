"use client";

import React, { useRef, useMemo, useState, useCallback } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import { motion, AnimatePresence } from "framer-motion";
import { Network, Route, X } from "lucide-react";
import * as THREE from "three";
import { useAIMStore } from "@/stores/aim-store";
import { SPRING } from "@/lib/utils";
import { computeRepulsion } from "@/lib/barnes-hut";
import { buildProvenanceNebulaMap, edgeColorFor } from "@/lib/provenance-map";

// ── Types ───────────────────────────────────────────────────────────────────

interface Node3D {
  id: string;
  label: string;
  type: string;
  labels: string[];
  properties: Record<string, unknown>;
  position: [number, number, number];
  color: string;
  radius: number;
}

interface Link3D {
  sourceId: string;
  targetId: string;
  type: string;
  color: string;
  /** Edge confidence in [0, 1]; drives static opacity when no hover/selection. */
  confidence?: number;
  /** Stable rel_id from backend — used to flag temporal-direction violations. */
  relId?: string;
}

// ── Colors by entity type ───────────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  Person:    "#60a5fa",
  Service:   "#34d399",
  Incident:  "#f87171",
  Decision:  "#a78bfa",
  Document:  "#fbbf24",
  Project:   "#2dd4bf",
  Component: "#fb923c",
  Team:      "#e879f9",
};

const DEFAULT_COLOR = "#94a3b8";

function getNodeColor(labels: string[]): string {
  for (const label of labels) {
    if (label !== "Entity" && TYPE_COLORS[label]) return TYPE_COLORS[label];
  }
  return DEFAULT_COLOR;
}

function getNodeRadius(labels: string[]): number {
  if (labels.includes("Service") || labels.includes("Team")) return 0.45;
  if (labels.includes("Person")) return 0.35;
  if (labels.includes("Incident")) return 0.4;
  return 0.3;
}

// ── 3D Force Layout (pre-computed) ──────────────────────────────────────────

function compute3DLayout(
  nodes: Node3D[],
  links: Link3D[],
  iterations: number = 120,
): void {
  const REPULSION = -2.0;
  const LINK_DISTANCE = 3.5;
  const LINK_STRENGTH = 0.15;
  const CENTER_STRENGTH = 0.03;
  const DAMPING = 0.85;

  // Initialize positions in a sphere
  const n = nodes.length || 1;
  const golden = (1 + Math.sqrt(5)) / 2;
  nodes.forEach((node, i) => {
    const theta = Math.acos(1 - (2 * (i + 0.5)) / n);
    const phi = 2 * Math.PI * i / golden;
    const r = 4 + Math.random() * 1;
    node.position = [
      r * Math.sin(theta) * Math.cos(phi),
      r * Math.sin(theta) * Math.sin(phi),
      r * Math.cos(theta),
    ];
  });

  const velocities = nodes.map(() => [0, 0, 0] as [number, number, number]);
  const nodeMap = new Map(nodes.map((n) => [n.id, nodes.indexOf(n)]));

  for (let iter = 0; iter < iterations; iter++) {
    const alpha = 1 - iter / iterations;

    // Center force
    for (let i = 0; i < nodes.length; i++) {
      for (let d = 0; d < 3; d++) {
        velocities[i][d] -= nodes[i].position[d] * CENTER_STRENGTH * alpha;
      }
    }

    // Repulsion (n-body) via Barnes-Hut octree — drops pairwise O(n²) to
    // O(n log n) so 1500-node adversarial clouds stay interactive.
    // θ=0.5 keeps per-node error within ~10% of exact pairwise (see
    // `frontend/__tests__/barnes-hut.test.ts`), which is below the
    // visual-noise floor of the per-frame damping we apply below.
    const bhPositions = nodes.map((n) => n.position) as [number, number, number][];
    const repulsion = computeRepulsion(bhPositions, REPULSION * alpha, 0.5);
    for (let i = 0; i < nodes.length; i++) {
      velocities[i][0] += repulsion[i][0];
      velocities[i][1] += repulsion[i][1];
      velocities[i][2] += repulsion[i][2];
    }

    // Link spring force
    for (const link of links) {
      const si = nodeMap.get(link.sourceId);
      const ti = nodeMap.get(link.targetId);
      if (si === undefined || ti === undefined) continue;
      const dx = nodes[ti].position[0] - nodes[si].position[0];
      const dy = nodes[ti].position[1] - nodes[si].position[1];
      const dz = nodes[ti].position[2] - nodes[si].position[2];
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.1;
      const displacement = (dist - LINK_DISTANCE) * LINK_STRENGTH * alpha;
      const fx = (dx / dist) * displacement;
      const fy = (dy / dist) * displacement;
      const fz = (dz / dist) * displacement;
      velocities[si][0] += fx;
      velocities[si][1] += fy;
      velocities[si][2] += fz;
      velocities[ti][0] -= fx;
      velocities[ti][1] -= fy;
      velocities[ti][2] -= fz;
    }

    // Apply velocity with damping
    for (let i = 0; i < nodes.length; i++) {
      for (let d = 0; d < 3; d++) {
        velocities[i][d] *= DAMPING;
        nodes[i].position[d] += velocities[i][d];
      }
    }
  }
}

// ── Nebula Node Component ───────────────────────────────────────────────────

function NebulaNode({
  node,
  isHovered,
  isSelected,
  onPointerOver,
  onPointerOut,
  onClick,
}: {
  node: Node3D;
  isHovered: boolean;
  isSelected: boolean;
  onPointerOver: () => void;
  onPointerOut: () => void;
  onClick: () => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);
  const targetScale = isHovered ? 1.5 : isSelected ? 1.3 : 1.0;
  const currentScale = useRef(1.0);

  useFrame(() => {
    if (!meshRef.current) return;
    currentScale.current += (targetScale - currentScale.current) * 0.12;
    const s = currentScale.current;
    meshRef.current.scale.setScalar(s);
    if (glowRef.current) {
      glowRef.current.scale.setScalar(s * 2.5);
    }
  });

  const color = new THREE.Color(node.color);

  return (
    <group position={node.position}>
      {/* Glow sphere */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[node.radius, 16, 16]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={isHovered ? 0.2 : isSelected ? 0.15 : 0.06}
        />
      </mesh>

      {/* Main sphere */}
      <mesh
        ref={meshRef}
        onPointerOver={(e) => { e.stopPropagation(); onPointerOver(); }}
        onPointerOut={onPointerOut}
        onClick={(e) => { e.stopPropagation(); onClick(); }}
      >
        <sphereGeometry args={[node.radius, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={isHovered ? 0.8 : isSelected ? 0.6 : 0.3}
          roughness={0.3}
          metalness={0.7}
        />
      </mesh>

      {/* Label (only when hovered or selected) */}
      {(isHovered || isSelected) && (
        <Html
          center
          distanceFactor={12}
          style={{ pointerEvents: "none" }}
          position={[0, node.radius + 0.5, 0]}
        >
          <div className="px-2 py-1 rounded-md bg-slate-900/95 border border-white/10 backdrop-blur-xl whitespace-nowrap">
            <p className="text-[9px] font-semibold text-white">{node.label}</p>
            <p className="text-[7px] font-mono text-slate-400">
              {node.labels.filter((l) => l !== "Entity").join(" / ")}
            </p>
          </div>
        </Html>
      )}
    </group>
  );
}

// ── Edge Lines ──────────────────────────────────────────────────────────────

function NebulaEdges({
  links,
  nodeMap,
  hoveredId,
  selectedId,
  violatingEdgeIds,
}: {
  links: Link3D[];
  nodeMap: Map<string, Node3D>;
  hoveredId: string | null;
  selectedId: string | null;
  violatingEdgeIds: Set<string>;
}) {
  const lineGeometries = useMemo(() => {
    return links.map((link) => {
      const source = nodeMap.get(link.sourceId);
      const target = nodeMap.get(link.targetId);
      if (!source || !target) return null;
      const points = [
        new THREE.Vector3(...source.position),
        new THREE.Vector3(...target.position),
      ];
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const isHighlighted =
        hoveredId === link.sourceId ||
        hoveredId === link.targetId ||
        selectedId === link.sourceId ||
        selectedId === link.targetId;
      // Confidence-driven base opacity: low-confidence edges fade, high-
      // confidence edges read clearly. Bounded to [0.08, 0.30] so the
      // graph never goes fully invisible or washes out dense clusters.
      const confidence = typeof link.confidence === "number" ? link.confidence : 1;
      const baseOpacity = 0.08 + Math.max(0, Math.min(1, confidence)) * 0.22;
      const isViolating = !!link.relId && violatingEdgeIds.has(link.relId);
      return {
        geometry,
        isHighlighted,
        type: link.type,
        baseOpacity,
        isViolating,
        color: link.color,
      };
    });
  }, [links, nodeMap, hoveredId, selectedId, violatingEdgeIds]);

  return (
    <group>
      {lineGeometries.map((item, i) => {
        if (!item) return null;
        // Temporal-direction violators read red and stay visible even when
        // not hovered — the whole point of the flag is catching the eye.
        const color = item.isViolating
          ? "#f87171"
          : item.isHighlighted
            ? "#60a5fa"
            : item.color;
        const opacity = item.isViolating
          ? 0.85
          : item.isHighlighted
            ? 0.6
            : item.baseOpacity;
        return (
          <line key={i}>
            <bufferGeometry attach="geometry" {...item.geometry} />
            <lineBasicMaterial
              attach="material"
              color={color}
              transparent
              opacity={opacity}
              linewidth={1}
            />
          </line>
        );
      })}
    </group>
  );
}

// ── Depth Fog + Ambient Particles ───────────────────────────────────────────

function NebulaParticles({ count = 200 }: { count?: number }) {
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 30;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 30;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 30;
    }
    return arr;
  }, [count]);

  const ref = useRef<THREE.Points>(null);

  useFrame((_, delta) => {
    if (ref.current) {
      ref.current.rotation.y += delta * 0.02;
      ref.current.rotation.x += delta * 0.01;
    }
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        color="#4b5563"
        size={0.04}
        transparent
        opacity={0.4}
        sizeAttenuation
      />
    </points>
  );
}

// ── Scene Content ───────────────────────────────────────────────────────────

function GraphScene({
  nodes,
  links,
  nodeMap,
  hoveredId,
  selectedId,
  setHoveredId,
  onNodeClick,
  violatingEdgeIds,
}: {
  nodes: Node3D[];
  links: Link3D[];
  nodeMap: Map<string, Node3D>;
  hoveredId: string | null;
  selectedId: string | null;
  setHoveredId: (id: string | null) => void;
  onNodeClick: (id: string) => void;
  violatingEdgeIds: Set<string>;
}) {
  return (
    <>
      <ambientLight intensity={0.3} />
      <pointLight position={[10, 10, 10]} intensity={0.8} color="#a5b4fc" />
      <pointLight position={[-10, -5, -10]} intensity={0.4} color="#6366f1" />

      <fog attach="fog" args={["#0a0a1a", 15, 45]} />

      <NebulaParticles />
      <NebulaEdges
        links={links}
        nodeMap={nodeMap}
        hoveredId={hoveredId}
        selectedId={selectedId}
        violatingEdgeIds={violatingEdgeIds}
      />

      {nodes.map((node) => (
        <NebulaNode
          key={node.id}
          node={node}
          isHovered={hoveredId === node.id}
          isSelected={selectedId === node.id}
          onPointerOver={() => setHoveredId(node.id)}
          onPointerOut={() => setHoveredId(null)}
          onClick={() => onNodeClick(node.id)}
        />
      ))}

      <OrbitControls
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.5}
        zoomSpeed={0.6}
        minDistance={3}
        maxDistance={30}
        enablePan={false}
      />
    </>
  );
}

// ── Main Component ──────────────────────────────────────────────────────────

function SelectedNodeTray({
  node,
  links,
  onClose,
}: {
  node: Node3D;
  links: Link3D[];
  onClose: () => void;
}) {
  const connected = links
    .filter((link) => link.sourceId === node.id || link.targetId === node.id)
    .slice(0, 6);
  const displayLabels = node.labels.filter((label) => label !== "Entity");
  const propertyEntries = Object.entries(node.properties ?? {})
    .filter(([, value]) => value != null && typeof value !== "object")
    .slice(0, 4);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.98 }}
      transition={SPRING.gentle}
      className="absolute right-3 top-3 w-[min(20rem,calc(100%-1.5rem))] rounded-lg border border-white/[0.08] bg-slate-950/85 p-3 shadow-2xl shadow-black/30 backdrop-blur-xl"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: node.color }}
            />
            <span className="mono-xs">Selected Entity</span>
          </div>
          <h3 className="truncate text-[12px] font-semibold text-slate-200">
            {node.label}
          </h3>
          <p className="mt-0.5 truncate text-[8px] font-mono uppercase tracking-wider text-slate-500">
            {displayLabels.join(" / ") || node.type}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 text-slate-600 transition-colors hover:bg-white/[0.06] hover:text-slate-300"
          aria-label="Clear selected entity"
          title="Clear selected entity"
        >
          <X size={13} />
        </button>
      </div>

      {connected.length > 0 && (
        <div className="mt-3 border-t border-white/[0.05] pt-2">
          <div className="mb-2 flex items-center gap-1.5">
            <Route size={10} className="text-blue-400/70" />
            <span className="mono-xs">Causal Edges</span>
          </div>
          <div className="space-y-1.5">
            {connected.map((link) => {
              const outgoing = link.sourceId === node.id;
              const otherId = outgoing ? link.targetId : link.sourceId;
              return (
                <div
                  key={`${link.sourceId}-${link.targetId}-${link.type}`}
                  className="flex items-center gap-2 rounded-md border border-white/[0.04] bg-white/[0.02] px-2 py-1.5"
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: link.color }}
                  />
                  <span className="truncate text-[8px] font-mono uppercase tracking-wider text-slate-500">
                    {outgoing ? "out" : "in"} / {link.type}
                  </span>
                  <span className="ml-auto max-w-[7rem] truncate text-right text-[8px] font-mono text-slate-600">
                    {otherId}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {propertyEntries.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-1.5">
          {propertyEntries.map(([key, value]) => (
            <div
              key={key}
              className="min-w-0 rounded-md border border-white/[0.04] bg-white/[0.02] px-2 py-1.5"
            >
              <div className="truncate text-[7px] font-mono uppercase tracking-wider text-slate-600">
                {key}
              </div>
              <div className="truncate text-[9px] text-slate-400">
                {String(value)}
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

export default function KnowledgeGraph() {
  const provenance = useAIMStore((s) => s.provenance);
  const selectedSourceId = useAIMStore((s) => s.selectedSourceId);
  const setSelectedSource = useAIMStore((s) => s.setSelectedSource);
  const status = useAIMStore((s) => s.status);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // ── Extract nodes + links from provenance ─────────────────────────────
  const { nodes3D, links3D, nodeMap, citedCount } = useMemo(() => {
    const nebula = buildProvenanceNebulaMap(provenance);
    if (!nebula.nodes.length) {
      return {
        nodes3D: [] as Node3D[],
        links3D: [] as Link3D[],
        nodeMap: new Map<string, Node3D>(),
        citedCount: 0,
      };
    }
    const graphEdges = provenance?.graph_edges ?? [];
    const graphNodes = provenance?.graph_nodes ?? [];

    const nodes: Node3D[] = nebula.nodes.map((gn) => ({
      id: gn.id,
      label: gn.label,
      type: gn.type,
      labels: gn.labels,
      properties: gn.properties,
      position: [0, 0, 0] as [number, number, number],
      color: getNodeColor(gn.labels),
      radius: gn.isCited ? getNodeRadius(gn.labels) * 1.18 : getNodeRadius(gn.labels),
    }));

    // Build links. Prefer authoritative `graph_edges` (directed, carry
    // confidence) over the legacy `relationship_path` reconstruction.
    // Dedup is direction-preserving: A→B and B→A stay distinct so causal
    // lineage reads correctly in the 3D view.
    const links: Link3D[] = [];
    const nodeIdSet = new Set(nodes.map((n) => n.id));
    const seenLinks = new Set<string>();

    if (graphEdges.length) {
      for (const edge of graphEdges) {
        if (!nodeIdSet.has(edge.source_entity_id) || !nodeIdSet.has(edge.target_entity_id)) {
          continue;
        }
        const key = `${edge.source_entity_id}→${edge.target_entity_id}:${edge.rel_type}`;
        if (seenLinks.has(key)) continue;
        seenLinks.add(key);
        links.push({
          sourceId: edge.source_entity_id,
          targetId: edge.target_entity_id,
          type: edge.rel_type,
          color: edgeColorFor(edge.rel_type),
          confidence: typeof edge.confidence === "number" ? edge.confidence : 1,
          relId: edge.rel_id,
        });
      }
    } else {
      // Fallback: reconstruct from relationship_path (no confidence available).
      for (const gn of graphNodes) {
        if (!gn.relationship_path) continue;
        for (const pathItem of gn.relationship_path) {
          const parts = pathItem.split(":");
          if (parts.length < 2) continue;
          const targetId = parts.slice(1).join(":");
          if (!nodeIdSet.has(targetId)) continue;
          const key = `${gn.entity_id}→${targetId}:${parts[0]}`;
          if (seenLinks.has(key)) continue;
          seenLinks.add(key);
          links.push({
            sourceId: gn.entity_id,
            targetId,
            type: parts[0],
            color: edgeColorFor(parts[0]),
          });
        }
      }
    }

    // Run 3D force simulation
    compute3DLayout(nodes, links);

    const map = new Map(nodes.map((n) => [n.id, n]));
    const citedCount = nodes.filter((node) => nebula.citedEntityIds.has(node.id)).length || nodes.length;
    return { nodes3D: nodes, links3D: links, nodeMap: map, citedCount };
  }, [provenance]);

  const handleNodeClick = useCallback(
    (id: string) => {
      setSelectedSource(selectedSourceId === id ? null : id);
    },
    [selectedSourceId, setSelectedSource],
  );

  const hasGraph = nodes3D.length > 0;
  const directionViolations = provenance?.direction_violations ?? 0;
  const violatingEdgeIds = useMemo(
    () => new Set(provenance?.violating_edge_ids ?? []),
    [provenance?.violating_edge_ids],
  );
  const selectedNode = selectedSourceId ? nodeMap.get(selectedSourceId) ?? null : null;

  return (
    <div className="glass-panel flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.04]">
        <div className="flex items-center gap-2">
          <Network size={14} className="text-blue-400/70" />
          <span className="label-xs text-slate-400">Knowledge Nebula</span>
          {hasGraph && (
            <span className="text-[9px] font-mono text-slate-600">
              {nodes3D.length}n · {links3D.length}e
            </span>
          )}
          {hasGraph && citedCount > 0 && (
            <span className="text-[9px] font-mono text-emerald-400/60">
              {citedCount} cited
            </span>
          )}
          {hasGraph && directionViolations > 0 && (
            <span
              className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-red-500/15 text-red-300 border border-red-500/30 animate-pulse"
              title={
                violatingEdgeIds.size > 0
                  ? `${directionViolations} causal edge(s) inverted vs timestamps — highlighted red in 3D`
                  : "Causal edges whose timestamps violated expected direction"
              }
            >
              {directionViolations} dir⚠
            </span>
          )}
        </div>
        {hasGraph && (
          <div className="flex items-center gap-1">
            <span className="text-[7px] font-mono text-slate-600 mr-1">
              Drag to orbit
            </span>
          </div>
        )}
      </div>

      {/* 3D Canvas / empty state */}
      <div className="flex-1 relative min-h-0">
        {hasGraph ? (
          <>
            <Canvas
              aria-label="3D provenance nebula"
              camera={{ position: [0, 0, 15], fov: 55, near: 0.1, far: 100 }}
              style={{ background: "transparent" }}
              gl={{ antialias: true, alpha: true }}
            >
              <GraphScene
                nodes={nodes3D}
                links={links3D}
                nodeMap={nodeMap}
                hoveredId={hoveredId}
                selectedId={selectedSourceId}
                setHoveredId={setHoveredId}
                onNodeClick={handleNodeClick}
                violatingEdgeIds={violatingEdgeIds}
              />
            </Canvas>

            <AnimatePresence>
              {selectedNode && (
                <SelectedNodeTray
                  node={selectedNode}
                  links={links3D}
                  onClose={() => setSelectedSource(null)}
                />
              )}
            </AnimatePresence>

            {/* Legend */}
            <div className="absolute bottom-2 left-2 flex flex-wrap gap-x-3 gap-y-1 px-2 py-1.5 rounded-lg bg-black/40 backdrop-blur-sm">
              {Object.entries(TYPE_COLORS).map(([type, color]) => (
                <div key={type} className="flex items-center gap-1">
                  <div
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-[7px] font-mono text-slate-500 uppercase">
                    {type}
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Network size={28} className="mx-auto text-slate-700 mb-2" />
              <p className="text-[10px] text-slate-600 font-mono">
                {status === "idle"
                  ? "3D nebula populates after a query"
                  : "Building knowledge nebula..."}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
