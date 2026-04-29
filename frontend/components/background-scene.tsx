"use client";

import React, { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Stars, PerspectiveCamera } from "@react-three/drei";
import {
  EffectComposer,
  Bloom,
  Noise,
  Vignette,
} from "@react-three/postprocessing";
import * as THREE from "three";
import { useAIMStore } from "@/stores/aim-store";

// ── Colors ──────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  idle: "#3b82f6",
  thinking: "#818cf8",
  streaming: "#818cf8",
  error: "#ef4444",
};

const ENTITY_TYPE_COLORS: Record<string, string> = {
  Person:    "#60a5fa",
  Service:   "#34d399",
  Incident:  "#f87171",
  Decision:  "#a78bfa",
  Document:  "#fbbf24",
  Project:   "#2dd4bf",
  Component: "#fb923c",
  Team:      "#e879f9",
};

// ── Decorative mode: live neural network (neurons + synapses + pulses) ─────
//
// Renders a brain-shaped cloud of "neurons" connected by "synapses". Pulses
// of light periodically travel along synapses, simulating action-potential
// firing. Neurons gently pulse in size to suggest activity. Speed and
// brightness scale up when AIM is thinking/streaming.
//
// Performance:
//   - 80 neurons via InstancedMesh (one draw call)
//   - ~200 synapses via single LineSegments buffer (one draw call)
//   - 24 traveling pulses via InstancedMesh (one draw call)
//   - All animation is per-frame matrix update, no React re-render

const NEURON_COUNT = 80;
const PULSE_COUNT = 24;
const SYNAPSE_MAX_DIST = 4.2; // world units

interface Neuron {
  pos: THREE.Vector3;
  pulsePhase: number;
  pulseSpeed: number;
}

interface Pulse {
  fromIdx: number;
  toIdx: number;
  t: number;       // 0..1 along the synapse
  speed: number;   // 1/seconds
}

function NeuralNetwork() {
  const status = useAIMStore((s) => s.status);
  const neuronMesh = useRef<THREE.InstancedMesh>(null!);
  const pulseMesh = useRef<THREE.InstancedMesh>(null!);
  const synapseRef = useRef<THREE.LineSegments>(null!);
  const dummy = useRef(new THREE.Object3D());
  const colorRef = useRef(new THREE.Color("#60a5fa"));
  const targetColor = useRef(new THREE.Color("#60a5fa"));

  // Build the network once. Neurons distributed in an oblate ellipsoid
  // (brain-shaped), synapses connect nearest neighbors within max distance.
  const { neurons, synapsePositions, synapseEnds } = useMemo(() => {
    // Brain-shaped ellipsoid: wider on X/Z, slightly squashed on Y.
    const RX = 14, RY = 9, RZ = 14;
    const ns: Neuron[] = [];
    for (let i = 0; i < NEURON_COUNT; i++) {
      // Random point inside ellipsoid (rejection sampling)
      let p: THREE.Vector3;
      while (true) {
        const x = (Math.random() * 2 - 1);
        const y = (Math.random() * 2 - 1);
        const z = (Math.random() * 2 - 1);
        if (x * x + y * y + z * z <= 1) {
          p = new THREE.Vector3(x * RX, y * RY, z * RZ);
          break;
        }
      }
      ns.push({
        pos: p,
        pulsePhase: Math.random() * Math.PI * 2,
        pulseSpeed: 0.6 + Math.random() * 0.8,
      });
    }

    // Build synapses: connect each neuron to nearby neighbors. Cap to
    // avoid every-pair explosion.
    const linePositions: number[] = [];
    const ends: Array<[number, number]> = [];
    for (let i = 0; i < NEURON_COUNT; i++) {
      let connected = 0;
      for (let j = i + 1; j < NEURON_COUNT && connected < 4; j++) {
        const d = ns[i].pos.distanceTo(ns[j].pos);
        if (d < SYNAPSE_MAX_DIST) {
          linePositions.push(
            ns[i].pos.x, ns[i].pos.y, ns[i].pos.z,
            ns[j].pos.x, ns[j].pos.y, ns[j].pos.z,
          );
          ends.push([i, j]);
          connected++;
        }
      }
    }

    return {
      neurons: ns,
      synapsePositions: new Float32Array(linePositions),
      synapseEnds: ends,
    };
  }, []);

  // Initialise the pulse pool — each pulse picks a random synapse to ride.
  const pulses = useRef<Pulse[]>(
    Array.from({ length: PULSE_COUNT }, () => {
      const synIdx = Math.floor(Math.random() * Math.max(synapseEnds.length, 1));
      const [from, to] = synapseEnds[synIdx] ?? [0, 0];
      return {
        fromIdx: from,
        toIdx: to,
        t: Math.random(),
        speed: 0.25 + Math.random() * 0.6,
      };
    }),
  );

  useFrame(({ clock }, delta) => {
    const t = clock.getElapsedTime();
    const active = status === "thinking" || status === "streaming";
    const speedScale = active ? 2.2 : 1.0;

    // Color interpolation toward status colour.
    targetColor.current.set(STATUS_COLORS[status] ?? "#60a5fa");
    colorRef.current.lerp(targetColor.current, 0.03);

    // Update neuron material colour.
    const nMat = neuronMesh.current.material as THREE.MeshStandardMaterial;
    nMat.color.copy(colorRef.current);
    nMat.emissive.copy(colorRef.current).multiplyScalar(0.7);
    nMat.emissiveIntensity = active ? 4.5 : 2.8;

    // Animate neurons (subtle size pulse).
    neurons.forEach((n, i) => {
      const pulse = Math.sin(t * n.pulseSpeed * speedScale + n.pulsePhase) * 0.5 + 1;
      const baseSize = 0.16;
      dummy.current.position.copy(n.pos);
      dummy.current.scale.setScalar(baseSize * (0.6 + pulse * 0.5));
      dummy.current.updateMatrix();
      neuronMesh.current.setMatrixAt(i, dummy.current.matrix);
    });
    neuronMesh.current.instanceMatrix.needsUpdate = true;

    // Animate pulses along synapses.
    if (synapseEnds.length > 0) {
      const pMat = pulseMesh.current.material as THREE.MeshStandardMaterial;
      pMat.color.copy(colorRef.current).multiplyScalar(1.4);
      pMat.emissive.copy(colorRef.current);
      pMat.emissiveIntensity = active ? 12 : 8;

      pulses.current.forEach((p, i) => {
        p.t += delta * p.speed * speedScale;
        if (p.t >= 1) {
          // Reassign to a new random synapse.
          const newIdx = Math.floor(Math.random() * synapseEnds.length);
          const [from, to] = synapseEnds[newIdx];
          p.fromIdx = from;
          p.toIdx = to;
          p.t = 0;
          p.speed = 0.25 + Math.random() * 0.6;
        }
        const a = neurons[p.fromIdx].pos;
        const b = neurons[p.toIdx].pos;
        dummy.current.position.set(
          a.x + (b.x - a.x) * p.t,
          a.y + (b.y - a.y) * p.t,
          a.z + (b.z - a.z) * p.t,
        );
        // Pulse fades in and out across its journey.
        const fade = Math.sin(p.t * Math.PI);
        dummy.current.scale.setScalar(0.13 * fade);
        dummy.current.updateMatrix();
        pulseMesh.current.setMatrixAt(i, dummy.current.matrix);
      });
      pulseMesh.current.instanceMatrix.needsUpdate = true;
    }

    // Synapse line opacity follows status colour brightness.
    if (synapseRef.current) {
      const lMat = synapseRef.current.material as THREE.LineBasicMaterial;
      lMat.color.copy(colorRef.current);
      lMat.opacity = active ? 0.18 : 0.10;
    }

    // Drift the whole network slowly so it never feels static.
    neuronMesh.current.rotation.y = t * 0.02;
    pulseMesh.current.rotation.y = t * 0.02;
    if (synapseRef.current) synapseRef.current.rotation.y = t * 0.02;
  });

  return (
    <>
      {/* Synapses (wires between neurons) */}
      {synapsePositions.length > 0 && (
        <lineSegments ref={synapseRef}>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              args={[synapsePositions, 3]}
            />
          </bufferGeometry>
          <lineBasicMaterial
            color="#60a5fa"
            transparent
            opacity={0.12}
            linewidth={1}
          />
        </lineSegments>
      )}

      {/* Neurons */}
      <instancedMesh
        ref={neuronMesh}
        args={[undefined, undefined, NEURON_COUNT]}
      >
        <sphereGeometry args={[1, 12, 12]} />
        <meshStandardMaterial
          color="#60a5fa"
          emissive="#1d4ed8"
          emissiveIntensity={3}
          toneMapped={false}
        />
      </instancedMesh>

      {/* Action-potential pulses traveling along synapses */}
      <instancedMesh
        ref={pulseMesh}
        args={[undefined, undefined, PULSE_COUNT]}
      >
        <sphereGeometry args={[1, 10, 10]} />
        <meshStandardMaterial
          color="#93c5fd"
          emissive="#60a5fa"
          emissiveIntensity={10}
          toneMapped={false}
        />
      </instancedMesh>
    </>
  );
}

// ── Data-driven mode: graph entity nodes in 3D space ────────────────────────

interface DataNode {
  x: number;
  y: number;
  z: number;
  size: number;
  color: THREE.Color;
  pulse: number;
}

function DataDrivenNodes() {
  const meshRef = useRef<THREE.InstancedMesh>(null!);
  const dummy = useRef(new THREE.Object3D());
  const provenance = useAIMStore((s) => s.provenance);
  const status = useAIMStore((s) => s.status);

  const dataNodes = useMemo<DataNode[]>(() => {
    const nodes = provenance?.graph_nodes;
    if (!nodes?.length) return [];

    const count = nodes.length;
    const spread = Math.min(20, 8 + count * 0.3);
    const goldenAngle = Math.PI * (3 - Math.sqrt(5)); // Fibonacci sphere

    return nodes.map((gn, i) => {
      // Fibonacci sphere distribution for even spacing
      const y = 1 - (i / (count - 1 || 1)) * 2; // -1 to 1
      const radiusAtY = Math.sqrt(1 - y * y);
      const theta = goldenAngle * i;

      const entityType = gn.labels.find((l) => l !== "Entity") || "Entity";
      const hex = ENTITY_TYPE_COLORS[entityType] || "#94a3b8";

      return {
        x: Math.cos(theta) * radiusAtY * spread,
        y: y * spread * 0.6,
        z: Math.sin(theta) * radiusAtY * spread,
        size: entityType === "Service" || entityType === "Team" ? 0.35 : 0.22,
        color: new THREE.Color(hex),
        pulse: Math.random() * Math.PI * 2,
      };
    });
  }, [provenance]);

  // Per-instance colors
  const colorArray = useMemo(() => {
    if (!dataNodes.length) return new Float32Array(0);
    const arr = new Float32Array(dataNodes.length * 3);
    dataNodes.forEach((n, i) => {
      arr[i * 3] = n.color.r;
      arr[i * 3 + 1] = n.color.g;
      arr[i * 3 + 2] = n.color.b;
    });
    return arr;
  }, [dataNodes]);

  useFrame(({ clock }) => {
    if (!dataNodes.length || !meshRef.current) return;
    const t = clock.getElapsedTime();
    const sp = status === "idle" ? 1 : 1.8;

    dataNodes.forEach((n, i) => {
      // Gentle orbit + breathing
      const orbitOffset = t * 0.15 * sp;
      const breathe = Math.sin(t * 0.6 + n.pulse) * 0.15 + 1;

      dummy.current.position.set(
        n.x * Math.cos(orbitOffset * 0.1) - n.z * Math.sin(orbitOffset * 0.1),
        n.y + Math.sin(t * 0.3 + n.pulse) * 0.5,
        n.x * Math.sin(orbitOffset * 0.1) + n.z * Math.cos(orbitOffset * 0.1),
      );
      dummy.current.scale.setScalar(n.size * breathe);
      dummy.current.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.current.matrix);
    });

    meshRef.current.instanceMatrix.needsUpdate = true;
    meshRef.current.rotation.y += 0.0003 * sp;
  });

  if (!dataNodes.length) return null;

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, dataNodes.length]}>
      <sphereGeometry args={[0.18, 14, 14]} />
      <meshStandardMaterial
        vertexColors
        emissive="#ffffff"
        emissiveIntensity={4}
        toneMapped={false}
      />
      {colorArray.length > 0 && (
        <instancedBufferAttribute
          attach="geometry-attributes-color"
          args={[colorArray, 3]}
        />
      )}
    </instancedMesh>
  );
}

// ── Connection lines between data nodes ─────────────────────────────────────

function DataConnections() {
  const provenance = useAIMStore((s) => s.provenance);
  const lineRef = useRef<THREE.LineSegments>(null!);

  const positions = useMemo(() => {
    const nodes = provenance?.graph_nodes;
    if (!nodes?.length || nodes.length < 2) return null;

    // Create connections between nodes that share relationship paths
    const nodeCount = nodes.length;
    const spread = Math.min(20, 8 + nodeCount * 0.3);
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));

    // Calculate positions (must match DataDrivenNodes)
    const positions3D = nodes.map((_, i) => {
      const y = 1 - (i / (nodeCount - 1 || 1)) * 2;
      const radiusAtY = Math.sqrt(1 - y * y);
      const theta = goldenAngle * i;
      return new THREE.Vector3(
        Math.cos(theta) * radiusAtY * spread,
        y * spread * 0.6,
        Math.sin(theta) * radiusAtY * spread,
      );
    });

    // Connect nearby nodes (distance-based connections for visual effect)
    const lines: number[] = [];
    const maxDist = spread * 0.8;
    for (let i = 0; i < nodeCount; i++) {
      for (let j = i + 1; j < nodeCount; j++) {
        const dist = positions3D[i].distanceTo(positions3D[j]);
        if (dist < maxDist) {
          lines.push(
            positions3D[i].x, positions3D[i].y, positions3D[i].z,
            positions3D[j].x, positions3D[j].y, positions3D[j].z,
          );
        }
      }
    }

    return new Float32Array(lines);
  }, [provenance]);

  useFrame(({ clock }) => {
    if (lineRef.current) {
      lineRef.current.rotation.y = clock.getElapsedTime() * 0.015;
    }
  });

  if (!positions || !positions.length) return null;

  return (
    <lineSegments ref={lineRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <lineBasicMaterial
        color="#3b82f6"
        transparent
        opacity={0.08}
        linewidth={1}
      />
    </lineSegments>
  );
}

// ── Scene switcher ──────────────────────────────────────────────────────────

function SceneContent() {
  const provenance = useAIMStore((s) => s.provenance);
  const hasGraphData = !!(provenance?.graph_nodes?.length);

  return (
    <>
      <Stars
        radius={120}
        depth={60}
        count={4000}
        factor={3}
        saturation={0}
        fade
        speed={0.6}
      />
      {hasGraphData ? (
        <>
          <DataDrivenNodes />
          <DataConnections />
        </>
      ) : (
        <NeuralNetwork />
      )}
    </>
  );
}

// ── Full-screen canvas background ────────────────────────────────────────────

export default function BackgroundScene() {
  return (
    <div className="fixed inset-0 z-0" aria-hidden="true">
      <Canvas dpr={[1, 1.5]}>
        <PerspectiveCamera makeDefault position={[0, 0, 32]} fov={55} />
        <color attach="background" args={["#030508"]} />
        <SceneContent />
        <EffectComposer enableNormalPass={false}>
          <Bloom
            intensity={2.2}
            luminanceThreshold={0.05}
            mipmapBlur
            radius={0.5}
          />
          <Noise opacity={0.025} />
          <Vignette darkness={1.3} offset={0.05} />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
