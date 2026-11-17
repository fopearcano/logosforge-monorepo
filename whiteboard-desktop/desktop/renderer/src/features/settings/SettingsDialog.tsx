/**
 * Application settings. Cloud folder controls are applied immediately; AI
 * settings are read/written through the Whiteboard backend passthrough. The API
 * key is write-only (blank keeps the stored one). "Test connection" saves the
 * current AI form, then round-trips a trivial prompt.
 */

import { useEffect, useRef, useState } from 'react';

import { ModalPortal } from '../../components/ModalPortal';
import { useModalDialog } from '../../components/useModalDialog';
import {
  cloudSyncStatusLabel,
  formatCloudSyncTime,
  type CloudSyncControls,
} from '../cloudSync/cloudSyncUi';
import {
  AI_PROVIDERS,
  PROVIDER_DEFAULT_URL,
  getAiSettings,
  saveAiSettings,
  settingsAfterProviderChange,
  testAiConnection,
  validateAiSettings,
  type AiSettings,
} from './settingsApi';
import type {
  NarrativePerson,
  NarrativeRegister,
  NarrativeStyle,
  SlangLevel,
} from '../whiteboard/documentSettings';
import type { DocumentSettingsApi } from '../whiteboard/useDocumentSettings';

interface Props {
  open: boolean;
  baseUrl: string;
  writingSettingsApi: DocumentSettingsApi;
  cloudSync?: CloudSyncControls;
  onClose: () => void;
}

const PERSONS: { value: NarrativePerson; label: string }[] = [
  { value: 'unspecified', label: 'Not specified' },
  { value: 'first', label: 'First person' },
  { value: 'third-limited', label: 'Third person — limited' },
  { value: 'third-omniscient', label: 'Third person — omniscient' },
];
const STYLES: { value: NarrativeStyle; label: string }[] = [
  { value: 'neutral', label: 'Neutral' },
  { value: 'literary', label: 'Literary' },
  { value: 'commercial', label: 'Commercial' },
  { value: 'cinematic', label: 'Cinematic' },
  { value: 'minimalist', label: 'Minimalist' },
  { value: 'lyrical', label: 'Lyrical' },
];
const REGISTERS: { value: NarrativeRegister; label: string }[] = [
  { value: 'neutral', label: 'Neutral' },
  { value: 'formal', label: 'Formal' },
  { value: 'standard', label: 'Standard' },
  { value: 'colloquial', label: 'Colloquial' },
  { value: 'vernacular', label: 'Vernacular' },
];
const SLANG_LEVELS: { value: SlangLevel; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'light', label: 'Light' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'heavy', label: 'Heavy' },
];

const EMPTY: AiSettings = { provider: 'LM Studio', model: '', base_url: '', timeout: 0 };

export function SettingsDialog({ open, baseUrl, writingSettingsApi, cloudSync, onClose }: Props) {
  const [form, setForm] = useState<AiSettings>(EMPTY);
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [test, setTest] = useState<{ ok: boolean; msg: string } | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const loadedProviderRef = useRef(EMPTY.provider);

  // The close button is always mounted, including while the provider form is
  // replaced by its loading state, so initial focus cannot fall back to <body>.
  useModalDialog({ open, dialogRef, initialFocusRef: closeRef, onClose });

  // Load current settings when opened.
  useEffect(() => {
    if (!open) return undefined;
    setStatus(null);
    setTest(null);
    setApiKey('');
    setLoading(true);
    const ctrl = new AbortController();
    getAiSettings(baseUrl, ctrl.signal)
      .then((s) => {
        const provider = s.provider || 'LM Studio';
        loadedProviderRef.current = provider;
        setForm({
          provider,
          model: s.model || '',
          base_url: s.base_url || '',
          timeout: s.timeout || 0,
        });
      })
      .catch(() => setStatus('Couldn’t load settings.'))
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [open, baseUrl]);

  if (!open) return null;

  const set = (patch: Partial<AiSettings>) => setForm((f) => ({ ...f, ...patch }));

  const selectProvider = (provider: string) => {
    // Provider transports are not interchangeable: carrying OpenAI's URL/model
    // into Anthropic produces /v1/v1/messages, while the reverse calls
    // api.anthropic.com/chat/completions. Reset all provider-specific fields and
    // require a fresh cloud key instead of silently reusing the prior key.
    setForm((current) => settingsAfterProviderChange(current, provider));
    setApiKey('');
    setStatus(null);
    setTest(null);
  };

  const validationError = (): string | null =>
    validateAiSettings(form, apiKey, loadedProviderRef.current);

  const buildPatch = (): Partial<AiSettings> => {
    const patch: Partial<AiSettings> = {
      provider: form.provider,
      model: form.model,
      base_url: form.base_url,
      timeout: form.timeout,
    };
    if (apiKey.trim()) patch.api_key = apiKey.trim();
    return patch;
  };

  const save = async () => {
    const invalid = validationError();
    if (invalid) {
      setStatus(invalid);
      return;
    }
    setSaving(true);
    setStatus(null);
    try {
      await saveAiSettings(baseUrl, buildPatch());
      loadedProviderRef.current = form.provider;
      setApiKey('');
      setStatus('Saved.');
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  const runTest = async () => {
    const invalid = validationError();
    if (invalid) {
      setTest({ ok: false, msg: invalid });
      return;
    }
    setTesting(true);
    setTest(null);
    try {
      await saveAiSettings(baseUrl, buildPatch()); // test what's on screen
      loadedProviderRef.current = form.provider;
      setApiKey('');
      const r = await testAiConnection(baseUrl);
      setTest(
        r.ok
          ? { ok: true, msg: `Connected — ${r.provider} responded.` }
          : { ok: false, msg: r.error || 'No response from the provider.' },
      );
    } catch (err: unknown) {
      setTest({ ok: false, msg: err instanceof Error ? err.message : 'Test failed.' });
    } finally {
      setTesting(false);
    }
  };

  const busy = saving || loading || testing;
  const writing = writingSettingsApi.settings;
  const updateWriting = writingSettingsApi.update;

  return (
    <ModalPortal>
      <div
        data-wb-modal-layer
        className="cf-overlay"
        onClick={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
      <div
        ref={dialogRef}
        className="settings-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="set-title"
        tabIndex={-1}
      >
        <div className="settings-head">
          <h2 id="set-title" className="settings-title">
            Settings
          </h2>
          <button ref={closeRef} type="button" className="settings-close" aria-label="Close settings" onClick={onClose}>
            ×
          </button>
        </div>
        <p className="settings-sub">Current-document writing defaults and the app-wide AI connection used by Billy &amp; Logos.</p>

        <h3 className="settings-section-title">Narrative voice</h3>
        <p className="settings-section-note">Used as guidance by Billy and Logos. Saved with this document and included in project bundles.</p>
        <div className="settings-form">
          <label className="settings-field">
            <span>Person</span>
            <select value={writing.narrativePerson} onChange={(e) => updateWriting('narrativePerson', e.target.value as NarrativePerson)}>
              {PERSONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="settings-field">
            <span>Style</span>
            <select value={writing.narrativeStyle} onChange={(e) => updateWriting('narrativeStyle', e.target.value as NarrativeStyle)}>
              {STYLES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="settings-field">
            <span>Register</span>
            <select value={writing.narrativeRegister} onChange={(e) => updateWriting('narrativeRegister', e.target.value as NarrativeRegister)}>
              {REGISTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="settings-field">
            <span>Slang</span>
            <select value={writing.slangLevel} onChange={(e) => updateWriting('slangLevel', e.target.value as SlangLevel)}>
              {SLANG_LEVELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        </div>

        {cloudSync && (
          <section className="cloud-sync-settings" aria-labelledby="cloud-sync-settings-title">
            <h3 id="cloud-sync-settings-title" className="settings-section-title">Cloud folder sync</h3>
            <p className="settings-section-note">
              Sync complete Whiteboard projects through a folder managed by Google Drive, Dropbox,
              OneDrive, iCloud Drive, Syncthing, or another desktop sync app. Whiteboard stores no
              cloud-account credentials.
            </p>
            <div className="cloud-sync-summary">
              <div className="cloud-sync-state" data-status={cloudSync.state.status} role="status" aria-live="polite">
                <span aria-hidden="true" />
                <strong>{cloudSyncStatusLabel(cloudSync.state.status)}</strong>
                {cloudSync.state.detail && <small>{cloudSync.state.detail}</small>}
              </div>
              <div className="cloud-sync-path">
                <span>Sync folder</span>
                <code title={cloudSync.state.folderPath ?? undefined}>
                  {cloudSync.state.folderPath ?? 'No folder selected'}
                </code>
              </div>
              <div className="cloud-sync-last">
                Last successful sync: <time>{formatCloudSyncTime(cloudSync.state.lastSuccessfulSyncAt)}</time>
              </div>
            </div>
            <label className="cloud-sync-automatic">
              <input
                type="checkbox"
                checked={cloudSync.state.automatic}
                disabled={!cloudSync.state.enabled || cloudSync.state.busy}
                onChange={(event) => void cloudSync.onAutomaticChange(event.target.checked)}
              />
              <span>Sync automatically</span>
            </label>
            <div className="cloud-sync-actions">
              <button type="button" className="settings-btn" disabled={cloudSync.state.busy} onClick={() => void cloudSync.onChooseFolder()}>
                Choose folder…
              </button>
              {cloudSync.state.status === 'folder-unavailable' || cloudSync.state.status === 'error' ? (
                <button type="button" className="settings-btn" disabled={cloudSync.state.busy} onClick={() => void cloudSync.onRetry()}>
                  Retry
                </button>
              ) : (
                <button type="button" className="settings-btn" disabled={!cloudSync.state.enabled || cloudSync.state.busy} onClick={() => void cloudSync.onSyncNow()}>
                  {cloudSync.state.status === 'syncing' ? 'Syncing…' : 'Sync now'}
                </button>
              )}
              {cloudSync.state.conflict && (
                <button type="button" className="settings-btn is-primary" disabled={cloudSync.state.busy} onClick={cloudSync.onReviewConflict}>
                  Review conflict
                </button>
              )}
              {cloudSync.state.enabled && (
                <button type="button" className="settings-btn cloud-sync-disable" disabled={cloudSync.state.busy} onClick={() => void cloudSync.onDisable()}>
                  Disable sync
                </button>
              )}
            </div>
            <p className="cloud-sync-safety">Local writing stays available while the folder or network is unavailable. Concurrent edits are preserved for review.</p>
          </section>
        )}

        <h3 className="settings-section-title">AI provider</h3>
        <p className="settings-section-note">Stored locally. A blank API-key field keeps the saved key for the current provider.</p>

        {loading ? (
          <p className="settings-hint">Loading…</p>
        ) : (
          <div className="settings-form">
            <label className="settings-field">
              <span>Provider</span>
              <select value={form.provider} onChange={(e) => selectProvider(e.target.value)}>
                {AI_PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>

            <label className="settings-field">
              <span>Base URL</span>
              <div className="settings-inline">
                <input
                  type="text"
                  spellCheck={false}
                  value={form.base_url}
                  placeholder={PROVIDER_DEFAULT_URL[form.provider] || 'https://…'}
                  onChange={(e) => set({ base_url: e.target.value })}
                />
                <button
                  type="button"
                  className="settings-mini"
                  title="Fill the default URL for this provider"
                  onClick={() => set({ base_url: PROVIDER_DEFAULT_URL[form.provider] || '' })}
                >
                  Default
                </button>
              </div>
            </label>

            <label className="settings-field">
              <span>Model</span>
              <input
                type="text"
                spellCheck={false}
                value={form.model}
                placeholder={
                  form.provider === 'OpenRouter'
                    ? 'e.g. anthropic/claude-opus-4-8 · openrouter/auto'
                    : 'e.g. llama-3.1-8b · gpt-4o · claude-sonnet-4-5'
                }
                onChange={(e) => set({ model: e.target.value })}
              />
            </label>

            <label className="settings-field">
              <span>API key</span>
              <input
                type="password"
                autoComplete="off"
                value={apiKey}
                placeholder="•••• (blank keeps the stored key)"
                onChange={(e) => setApiKey(e.target.value)}
              />
            </label>

            <label className="settings-field">
              <span>Timeout (s)</span>
              <input
                type="number"
                min={0}
                value={form.timeout}
                onChange={(e) => set({ timeout: Number(e.target.value) || 0 })}
              />
            </label>
          </div>
        )}

        {test && <div className={`settings-test ${test.ok ? 'is-ok' : 'is-err'}`}>{test.msg}</div>}

        <div className="settings-actions">
          <button type="button" className="settings-btn" onClick={runTest} disabled={busy}>
            {testing ? 'Testing…' : 'Test connection'}
          </button>
          <span className="settings-status" aria-live="polite">
            {status}
          </span>
          <button type="button" className="settings-btn is-primary" onClick={save} disabled={busy}>
            {saving ? 'Saving…' : 'Save AI settings'}
          </button>
        </div>
      </div>
      </div>
    </ModalPortal>
  );
}
