export type RuntimeFaultSource = 'event' | 'promise';

export interface RuntimeFault {
  source: RuntimeFaultSource;
  name: string;
  message: string;
  details: string;
  key: string;
  occurredAt: number;
}

export interface PreviousRuntimeFault {
  key: string;
  occurredAt: number;
}

const handledErrors = new WeakSet<object>();

function isWeakKey(value: unknown): value is object {
  return (typeof value === 'object' && value !== null) || typeof value === 'function';
}

function asError(value: unknown): Error | null {
  try {
    return value instanceof Error ? value : null;
  } catch {
    // A hostile Proxy can throw while JavaScript walks its prototype chain.
    return null;
  }
}

function stringField(value: unknown, field: string): string {
  if (!isWeakKey(value)) return '';
  try {
    const candidate = (value as Record<string, unknown>)[field];
    return typeof candidate === 'string' ? candidate : '';
  } catch {
    return '';
  }
}

function readableValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value == null) return String(value);
  try {
    const encoded = JSON.stringify(value);
    if (encoded) return encoded;
  } catch {
    // Cyclic values and hostile toJSON/proxy traps use the safe fallback below.
  }
  try {
    return String(value);
  } catch {
    return 'Unknown runtime error';
  }
}

function compact(value: string, limit: number): string {
  const normalized = value.replace(/\s+/g, ' ').trim() || 'Unknown runtime error';
  return normalized.length > limit ? `${normalized.slice(0, limit - 1)}…` : normalized;
}

export function markRuntimeFaultHandled(reason: unknown): void {
  if (isWeakKey(reason)) handledErrors.add(reason);
}

export function wasRuntimeFaultHandled(reason: unknown): boolean {
  return isWeakKey(reason) && handledErrors.has(reason);
}

export function isExpectedCancellation(reason: unknown): boolean {
  const name = stringField(reason, 'name');
  const code = stringField(reason, 'code');
  return name === 'AbortError' || code === 'ABORT_ERR';
}

export function createRuntimeFault(
  source: RuntimeFaultSource,
  reason: unknown,
  occurredAt = Date.now(),
): RuntimeFault {
  const error = asError(reason);
  const observedName = stringField(reason, 'name');
  const observedMessage = stringField(reason, 'message');
  const observedStack = stringField(reason, 'stack');
  const name = compact(observedName || 'Error', 80);
  const rawMessage = error
    ? observedMessage || observedName
    : observedMessage || readableValue(reason);
  const message = compact(rawMessage, 600);
  const rawDetails = error
    ? observedStack || `${name}: ${message}`
    : observedStack || readableValue(reason);
  const details = rawDetails.slice(0, 4000);
  return { source, name, message, details, key: `${name}:${message}`, occurredAt };
}

export function shouldReportRuntimeFault(
  previous: PreviousRuntimeFault | null,
  next: RuntimeFault,
  dedupeWindowMs = 5000,
): boolean {
  if (!previous || previous.key !== next.key) return true;
  return next.occurredAt - previous.occurredAt >= Math.max(0, dedupeWindowMs);
}
