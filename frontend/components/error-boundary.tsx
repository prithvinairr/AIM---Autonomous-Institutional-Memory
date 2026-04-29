"use client";

import React, { Component, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallbackLabel?: string;
  panelName?: string;
  onRetry?: () => void;
}

interface State {
  hasError: boolean;
  errorMessage?: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error.message };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(
      `[ErrorBoundary${this.props.panelName ? `:${this.props.panelName}` : ""}]`,
      error,
      info.componentStack,
    );
  }

  private handleRetry = () => {
    this.setState({ hasError: false, errorMessage: undefined });
    this.props.onRetry?.();
  };

  render() {
    if (this.state.hasError) {
      const label =
        this.props.fallbackLabel ||
        (this.props.panelName
          ? `${this.props.panelName} encountered an error.`
          : "This panel encountered an error.");

      return (
        <div className="flex flex-col items-center justify-center gap-3 p-6 glass-panel min-h-[120px]">
          <AlertTriangle size={16} className="text-red-400/70" />
          <p className="text-[10px] font-mono text-slate-500 text-center">
            {label}
          </p>
          {this.state.errorMessage && (
            <p className="text-[8px] font-mono text-slate-600 text-center max-w-[200px] truncate">
              {this.state.errorMessage}
            </p>
          )}
          <button
            onClick={this.handleRetry}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.04] border border-white/[0.07] text-[9px] font-mono text-slate-400 hover:text-white hover:bg-white/[0.08] transition-colors"
          >
            <RefreshCw size={10} />
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
