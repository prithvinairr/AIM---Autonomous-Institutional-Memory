/**
 * Tests for the ErrorBoundary component — error catching, retry, and panelName.
 */
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import ErrorBoundary from "@/components/error-boundary";

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test crash");
  return <div data-testid="child-content">Content is fine</div>;
}

describe("ErrorBoundary", () => {
  // Suppress expected console.error from ErrorBoundary
  const originalError = console.error;
  beforeEach(() => {
    console.error = vi.fn();
  });
  afterEach(() => {
    console.error = originalError;
  });

  it("renders children when no error occurs", () => {
    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("child-content")).toBeInTheDocument();
  });

  it("displays fallback UI when child throws", () => {
    render(
      <ErrorBoundary panelName="TestPanel">
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.queryByTestId("child-content")).not.toBeInTheDocument();
    expect(screen.getByText(/TestPanel encountered an error/)).toBeInTheDocument();
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });

  it("displays custom fallbackLabel when provided", () => {
    render(
      <ErrorBoundary fallbackLabel="Custom error message">
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Custom error message")).toBeInTheDocument();
  });

  it("displays error message details", () => {
    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Test crash")).toBeInTheDocument();
  });

  it("recovers on retry click", () => {
    // Use a mutable flag instead of re-render approach
    let shouldThrow = true;
    function Toggler() {
      if (shouldThrow) throw new Error("Boom");
      return <div data-testid="recovered">Recovered!</div>;
    }

    const { rerender } = render(
      <ErrorBoundary panelName="Test">
        <Toggler />
      </ErrorBoundary>,
    );

    // Should be in error state
    expect(screen.getByText("Retry")).toBeInTheDocument();

    // Fix the child and retry
    shouldThrow = false;
    fireEvent.click(screen.getByText("Retry"));

    // Should recover
    expect(screen.getByTestId("recovered")).toBeInTheDocument();
  });

  it("calls onRetry callback when provided", () => {
    const onRetry = vi.fn();
    let shouldThrow = true;
    function Toggler() {
      if (shouldThrow) throw new Error("Boom");
      return <div>OK</div>;
    }

    render(
      <ErrorBoundary onRetry={onRetry}>
        <Toggler />
      </ErrorBoundary>,
    );

    shouldThrow = false;
    fireEvent.click(screen.getByText("Retry"));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
