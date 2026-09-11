import {
  Component,
  createRef,
  type CSSProperties,
  type ErrorInfo,
  type ReactNode,
} from 'react';

import { createRuntimeFault, markRuntimeFaultHandled } from './runtimeFaults';

const contentStyle: CSSProperties = {
  minWidth: 0,
  minHeight: 0,
  outline: 'none',
};

const fallbackStyle: CSSProperties = {
  minWidth: 0,
  minHeight: 180,
  boxSizing: 'border-box',
  display: 'grid',
  placeItems: 'center',
  padding: 24,
  background: 'var(--paper, #fff)',
  color: 'var(--text, #252422)',
  fontFamily: 'var(--font-ui, sans-serif)',
};

const cardStyle: CSSProperties = {
  width: 'min(560px, 100%)',
  boxSizing: 'border-box',
  border: '1px solid var(--error, #c0473b)',
  borderRadius: 'var(--r-lg, 8px)',
  background: 'var(--panel-2, #fff)',
  boxShadow: 'var(--page-shadow, 0 18px 60px rgba(0, 0, 0, .25))',
  padding: '18px 20px',
};

export interface RenderErrorBoundaryProps {
  name: string;
  children: ReactNode;
  /** Applied to both the normal content root and the fallback root. */
  className?: string;
  /** Changing this value clears a captured error and mounts the new scope. */
  resetKey?: unknown;
  onError?: (error: Error, info: ErrorInfo) => void;
  onReset?: () => void;
}

interface RenderErrorBoundaryState {
  error: Error | null;
}

function normalizedError(value: unknown): Error {
  const fault = createRuntimeFault('event', value);
  const error = new Error(fault.message);
  error.name = fault.name;
  error.stack = fault.details;
  return error;
}

function rootClass(base: string, className?: string): string {
  return className ? `${base} ${className}` : base;
}

/** Contains a broken renderer region and offers a local, focus-safe retry. */
export class RenderErrorBoundary extends Component<
  RenderErrorBoundaryProps,
  RenderErrorBoundaryState
> {
  state: RenderErrorBoundaryState = { error: null };
  private readonly contentRef = createRef<HTMLDivElement>();
  private focusAfterRecovery = false;

  static getDerivedStateFromError(error: unknown): RenderErrorBoundaryState {
    return { error: normalizedError(error) };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.focusAfterRecovery = false;
    markRuntimeFaultHandled(error);
    // Preserve the component stack in developer diagnostics while presenting a
    // concise, local recovery surface to the writer.
    console.error(`[LogosForge Whiteboard] ${this.props.name} render failed`, error, info.componentStack);
    try {
      this.props.onError?.(normalizedError(error), info);
    } catch (reportingError) {
      console.error(
        `[LogosForge Whiteboard] ${this.props.name} error reporter failed`,
        reportingError,
      );
    }
  }

  componentDidUpdate(
    previous: RenderErrorBoundaryProps,
    previousState: RenderErrorBoundaryState,
  ): void {
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
        <div
          ref={this.contentRef}
          className={rootClass('render-error-content', this.props.className)}
          role="region"
          aria-label={`${this.props.name} content`}
          data-ui-error-content={this.props.name}
          tabIndex={-1}
          style={contentStyle}
        >
          {this.props.children}
        </div>
      );
    }

    const message = (error.message || 'Unknown rendering error').slice(0, 600);
    return (
      <div
        className={rootClass('render-error-fallback', this.props.className)}
        role="alert"
        aria-atomic="true"
        data-ui-error-boundary={this.props.name}
        style={fallbackStyle}
      >
        <div style={cardStyle}>
          <div
            style={{
              marginBottom: 8,
              color: 'var(--error, #c0473b)',
              fontFamily: 'var(--font-mono, monospace)',
              fontSize: 9,
              fontWeight: 600,
              letterSpacing: '.14em',
            }}
          >
            RENDER RECOVERY
          </div>
          <div style={{ marginBottom: 8, color: 'var(--text, #252422)', fontSize: 15, fontWeight: 700 }}>
            {this.props.name} is temporarily unavailable
          </div>
          <div style={{ color: 'var(--muted, #716f69)', fontSize: 11.5, lineHeight: 1.55, overflowWrap: 'anywhere' }}>
            {message}
          </div>
          <div style={{ marginTop: 10, color: 'var(--muted, #716f69)', fontSize: 10, lineHeight: 1.5 }}>
            Retry remounts only this area.
          </div>
          <button
            type="button"
            onClick={this.retry}
            aria-label={`Retry ${this.props.name}`}
            style={{
              marginTop: 14,
              border: '1px solid var(--accent, #b0653f)',
              borderRadius: 'var(--r-sm, 4px)',
              background: 'transparent',
              color: 'var(--accent, #b0653f)',
              padding: '7px 13px',
              font: 'inherit',
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: '.08em',
              cursor: 'pointer',
            }}
          >
            Retry {this.props.name}
          </button>
        </div>
      </div>
    );
  }
}
