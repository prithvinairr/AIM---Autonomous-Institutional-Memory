/**
 * Tests for lib/utils — cn(), SPRING presets, formatTokens, formatCost, API_BASE.
 */
import { describe, it, expect } from "vitest";
import { cn, SPRING, formatTokens, formatCost, API_BASE } from "@/lib/utils";

describe("cn() — Tailwind class merging", () => {
  it("merges simple classes", () => {
    expect(cn("text-red-500", "bg-blue-500")).toBe("text-red-500 bg-blue-500");
  });

  it("resolves conflicts by keeping last", () => {
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("handles conditional classes", () => {
    const active = true;
    const result = cn("base", active && "active-class", !active && "inactive");
    expect(result).toContain("active-class");
    expect(result).not.toContain("inactive");
  });

  it("handles empty and falsy values", () => {
    expect(cn("", undefined, null, false, "real")).toBe("real");
  });
});

describe("SPRING presets", () => {
  it("has all expected presets", () => {
    expect(SPRING.snappy).toBeDefined();
    expect(SPRING.gentle).toBeDefined();
    expect(SPRING.bouncy).toBeDefined();
    expect(SPRING.slow).toBeDefined();
    expect(SPRING.swift).toBeDefined();
  });

  it("all presets are spring type", () => {
    for (const preset of Object.values(SPRING)) {
      expect(preset.type).toBe("spring");
      expect(preset.stiffness).toBeGreaterThan(0);
      expect(preset.damping).toBeGreaterThan(0);
    }
  });
});

describe("formatTokens()", () => {
  it("formats thousands with separator", () => {
    const result = formatTokens(1234);
    expect(result).toMatch(/1.234|1,234/); // locale-dependent
  });

  it("handles zero", () => {
    expect(formatTokens(0)).toBe("0");
  });
});

describe("formatCost()", () => {
  it("shows 6 decimal places for very small costs", () => {
    expect(formatCost(0.000123)).toBe("$0.000123");
  });

  it("shows 5 decimal places for small costs", () => {
    expect(formatCost(0.00456)).toBe("$0.00456");
  });

  it("shows 4 decimal places for normal costs", () => {
    expect(formatCost(0.1234)).toBe("$0.1234");
  });
});

describe("API_BASE", () => {
  it("uses same-origin proxy routes", () => {
    expect(API_BASE).toBe("");
  });
});
