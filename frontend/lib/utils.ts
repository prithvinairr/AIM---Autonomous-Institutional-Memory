import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes with clsx — same pattern as shadcn/ui */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Spring presets — Apple HIG / Google Material motion language */
export const SPRING = {
  snappy:  { type: "spring" as const, stiffness: 500, damping: 40 },
  gentle:  { type: "spring" as const, stiffness: 280, damping: 32 },
  bouncy:  { type: "spring" as const, stiffness: 420, damping: 26 },
  slow:    { type: "spring" as const, stiffness: 180, damping: 28 },
  swift:   { type: "spring" as const, stiffness: 600, damping: 45 },
};

/** Format token count with locale separator */
export function formatTokens(n: number): string {
  return n.toLocaleString();
}

/** Format USD cost to appropriate precision */
export function formatCost(usd: number): string {
  if (usd < 0.001) return `$${usd.toFixed(6)}`;
  if (usd < 0.01) return `$${usd.toFixed(5)}`;
  return `$${usd.toFixed(4)}`;
}

/** Browser requests stay same-origin so backend credentials remain server-side. */
export const API_BASE = "";
