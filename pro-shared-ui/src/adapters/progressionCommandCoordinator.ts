import type { ProgressionCommandDTO } from "@logosforge/ui-contracts";

/** Minimal storage surface shared by Window.localStorage and async host stores. */
export interface ProgressionCommandStorage {
  getItem(key: string): Promise<string | null> | string | null;
  setItem(key: string, value: string): Promise<void> | void;
  removeItem(key: string, expectedValue?: string): Promise<boolean | void> | boolean | void;
}

export interface PendingProgressionCommand {
  projectId: number;
  command: ProgressionCommandDTO;
  key: string;
  resendAttempted: boolean;
  receiptOnly: boolean;
}

export interface StoredProgressionCommand {
  saveKey: string;
  pending: PendingProgressionCommand;
}

interface StoredEnvelope extends StoredProgressionCommand {
  version: 1;
  scope: string;
  storedAt: number;
}

const STORAGE_PREFIX = "logosforge.pro.progressions.pending.v1";
const COMMAND_KINDS = new Set<ProgressionCommandDTO["kind"]>([
  "create_track",
  "update_track",
  "delete_track",
  "reorder_tracks",
  "create_beat",
  "update_beat",
  "delete_beat",
  "reorder_beats",
]);
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/;
const REVISION = /^[0-9a-f]{64}$/;

// This process-local mirror keeps recovery alive when a StudioProvider subtree
// is replaced even if storage is temporarily unreadable. Durable storage is the
// authority across a full renderer/app restart.
const memoryMirror = new Map<string, string>();

function clone<T>(value: T): T {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

function normalizedScope(scope: string | undefined): string {
  const candidate = scope?.trim();
  return candidate ? candidate.slice(0, 200) : "default";
}

function storageKey(scope: string, projectId: number): string {
  return `${STORAGE_PREFIX}:${encodeURIComponent(scope)}:${projectId}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function parseEnvelope(raw: string, scope: string, projectId: number): StoredEnvelope | null {
  let value: unknown;
  try { value = JSON.parse(raw); } catch { return null; }
  if (!isRecord(value) || value.version !== 1 || value.scope !== scope) return null;
  if (typeof value.saveKey !== "string" || !value.saveKey.trim() || value.saveKey.length > 512) return null;
  if (typeof value.storedAt !== "number" || !Number.isFinite(value.storedAt)) return null;
  if (!isRecord(value.pending)) return null;
  const pending = value.pending;
  if (pending.projectId !== projectId || !Number.isSafeInteger(projectId) || projectId <= 0) return null;
  if (typeof pending.key !== "string" || !IDEMPOTENCY_KEY.test(pending.key)) return null;
  if (typeof pending.resendAttempted !== "boolean" || typeof pending.receiptOnly !== "boolean") return null;
  if (!isRecord(pending.command)
    || typeof pending.command.kind !== "string"
    || !COMMAND_KINDS.has(pending.command.kind as ProgressionCommandDTO["kind"])
    || typeof pending.command.expected_revision !== "string"
    || !REVISION.test(pending.command.expected_revision)) return null;
  return value as unknown as StoredEnvelope;
}

export function progressionCommandStorageForWindow(
  ownerWindow?: Window | null,
): ProgressionCommandStorage | null {
  try {
    if (ownerWindow?.localStorage) return ownerWindow.localStorage;
  } catch {
    // Detached/locked-down realms may reject localStorage access.
  }
  try {
    // Avoid invoking Node's experimental localStorage getter during SSR/tests.
    // Browser panels arrive through ownerWindow above; an explicitly installed
    // test/polyfill value is still accepted here.
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
    return descriptor && "value" in descriptor
      ? descriptor.value as ProgressionCommandStorage | null
      : null;
  } catch {
    return null;
  }
}

/**
 * Durable exact-command store for Progressions receipt recovery.
 *
 * A scope identifies one backing Core/account, and each project gets one
 * unresolved command slot. Removal is compare-by-save-key so a stale panel can
 * never erase a newer delivery written by another mounted surface.
 */
export class ProgressionCommandCoordinator {
  readonly scope: string;
  private readonly storage: ProgressionCommandStorage | null;

  constructor(
    scope?: string,
    storage: ProgressionCommandStorage | null = progressionCommandStorageForWindow(),
  ) {
    this.scope = normalizedScope(scope);
    this.storage = storage;
  }

  async load(projectId: number): Promise<StoredProgressionCommand | null> {
    if (!Number.isSafeInteger(projectId) || projectId <= 0) return null;
    const key = storageKey(this.scope, projectId);
    let raw: string | null = null;
    const storageRead = this.storage != null;
    if (this.storage) raw = await this.storage.getItem(key);
    else raw = memoryMirror.get(key) ?? null;
    if (raw == null) {
      if (storageRead) memoryMirror.delete(key);
      return null;
    }
    const parsed = parseEnvelope(raw, this.scope, projectId);
    if (!parsed) {
      memoryMirror.delete(key);
      try { await this.storage?.removeItem(key, raw); } catch { /* best effort */ }
      return null;
    }
    memoryMirror.set(key, raw);
    return clone({ saveKey: parsed.saveKey, pending: parsed.pending });
  }

  /** Save before transport begins. Returns false only when no durable storage accepted it. */
  async save(saveKey: string, pending: PendingProgressionCommand): Promise<boolean> {
    const projectId = pending.projectId;
    const envelope: StoredEnvelope = {
      version: 1,
      scope: this.scope,
      storedAt: Date.now(),
      saveKey,
      pending: clone(pending),
    };
    const raw = JSON.stringify(envelope);
    if (!parseEnvelope(raw, this.scope, projectId)) {
      throw new Error("Refusing to persist an invalid Progressions recovery command.");
    }
    const key = storageKey(this.scope, projectId);
    if (!this.storage) return false;
    try {
      await this.storage.setItem(key, raw);
      memoryMirror.set(key, raw);
      return true;
    } catch {
      return false;
    }
  }

  async remove(projectId: number, expectedSaveKey?: string): Promise<boolean> {
    const current = await this.load(projectId);
    if (current == null) {
      // The host may have committed the compare-remove tombstone before its IPC
      // response was lost. Retrying that exact absence is idempotent success.
      memoryMirror.delete(storageKey(this.scope, projectId));
      return true;
    }
    if (expectedSaveKey != null && current?.saveKey !== expectedSaveKey) return false;
    const key = storageKey(this.scope, projectId);
    if (!this.storage) return false;
    const expectedValue = memoryMirror.get(key);
    try {
      const removed = await this.storage.removeItem(key, expectedValue);
      if (removed === false) return false;
      memoryMirror.delete(key);
      return true;
    } catch {
      // A stale safe record is preferable to data loss.
      return false;
    }
  }
}

/** Test-only process boundary simulation; durable storage is deliberately kept. */
export function resetProgressionCommandMemoryForTests(): void {
  memoryMirror.clear();
}
