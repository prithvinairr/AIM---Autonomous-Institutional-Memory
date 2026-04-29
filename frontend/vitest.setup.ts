import "@testing-library/jest-dom/vitest";

// ── ResizeObserver mock ─────────────────────────────────────────────────────
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverMock as any;

// ── matchMedia mock ─────────────────────────────────────────────────────────
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// ── crypto.randomUUID mock ──────────────────────────────────────────────────
if (!globalThis.crypto?.randomUUID) {
  Object.defineProperty(globalThis, "crypto", {
    value: {
      randomUUID: () => "test-uuid-" + Math.random().toString(36).slice(2, 10),
    },
  });
}

// ── IntersectionObserver mock ───────────────────────────────────────────────
class IntersectionObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.IntersectionObserver = IntersectionObserverMock as any;
