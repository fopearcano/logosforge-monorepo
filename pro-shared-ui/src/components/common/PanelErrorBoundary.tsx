import { Component, createRef, type CSSProperties, type ErrorInfo, type ReactNode } from "react";
import { markRuntimeFaultHandled } from "./runtimeFaults";

const fallbackStyle: CSSProperties = {
  width: "100%",
  height: "100%",
  minHeight: 180,
  display: "grid",
  placeItems: "center",
  padding: 24,
  background: "linear-gradient(180deg,var(--panel,#080a0f),var(--base,#04060a))",
  color: "var(--txt,#e4e8ef)",
  fontFamily: "'JetBrains Mono',monospace",
};

const cardStyle: CSSProperties = {
  width: "min(560px,100%)",
  border: "1px solid var(--crimson,#e8443a)",
  background: "var(--raised,#11151e)",
  boxShadow: "0 18px 60px rgba(0,0,0,.45)",
  padding: "18px 20px",
};

export interface PanelErrorBoundaryProps {
  name: string;
  children: ReactNode;
  /** Changing this value clears a captured error and mounts the new scope. */
  resetKey?: unknown;
  onError?: (error: Error, info: ErrorInfo) => void;
  onReset?: () => void;
}

interface PanelErrorBoundaryState {
  error: Error | null;
}

function normalizedError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

/** Keeps a broken panel from taking down the rest of the writing workspace. */
export class PanelErrorBoundary extends Component<PanelErrorBoundaryProps, PanelErrorBoundaryState> {
  state: PanelErrorBoundaryState = { error: null };
  private readonly contentRef = createRef<HTMLDivElement>();
  private focusAfterRecovery = false;

  static getDerivedStateFromError(error: unknown): PanelErrorBoundaryState {
    return { error: normalizedError(error) };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.focusAfterRecovery = false;
    markRuntimeFaultHandled(error);
    // Keep the full component stack in developer diagnostics; the writer sees
    // the concise message and a local recovery action in the fallback below.
    console.error(`[LogosForge] ${this.props.name} render failed`, error, info.componentStack);
    try {
      this.props.onError?.(normalizedError(error), info);
    } catch (reportingError) {
      console.error(`[LogosForge] ${this.props.name} error reporter failed`, reportingError);
    }
  }

  componentDidUpdate(previous: PanelErrorBoundaryProps, previousState: PanelErrorBoundaryState): void {
    if (this.state.error && !Object.is(previous.resetKey, this.props.resetKey)) {
      this.setState({ error: null });
      return;
    }
    if (this.focusAfterRecovery && previousState.error && !this.state.error) {
      this.focusAfterRecovery = false;
      this.contentRef.current?.focus({ preventScroll: true });
    }
  }

  private retry = (): void => {
    this.focusAfterRecovery = true;
    this.props.onReset?.();
    this.setState({ error: null });
  };

  render(): ReactNode {
    const error = this.state.error;
    if (!error) {
      return (
        <div ref={this.contentRef} role="region" aria-label={`${this.props.name} content`} data-ui-error-content={this.props.name} tabIndex={-1} style={{ width: "100%", height: "100%", minHeight: 0, outline: "none" }}>
          {this.props.children}
        </div>
      );
    }
    const message = (error.message || "Unknown rendering error").slice(0, 600);

    return (
      <div role="alert" data-ui-error-boundary={this.props.name} style={fallbackStyle}>
        <div style={cardStyle}>
          <div style={{ color: "var(--crimson,#e8443a)", fontSize: 9, letterSpacing: ".18em", marginBottom: 8 }}>PANEL RECOVERY</div>
          <div style={{ color: "var(--strong,#fff)", fontSize: 15, fontWeight: 700, marginBottom: 8 }}>{this.props.name} is temporarily unavailable</div>
          <div style={{ color: "var(--txt2,#8b95a5)", fontSize: 11, lineHeight: 1.55, overflowWrap: "anywhere" }}>{message}</div>
          <div style={{ color: "var(--txt3,#525c6b)", fontSize: 9, lineHeight: 1.5, marginTop: 10 }}>Your project data is unchanged. Retry remounts only this area.</div>
          <button type="button" onClick={this.retry} style={{ marginTop: 14, border: "1px solid var(--cyan,#4cc2ff)", background: "transparent", color: "var(--cyan,#4cc2ff)", padding: "7px 13px", font: "inherit", fontSize: 9.5, letterSpacing: ".1em", cursor: "pointer" }}>RETRY {this.props.name.toUpperCase()}</button>
        </div>
      </div>
    );
  }
}
