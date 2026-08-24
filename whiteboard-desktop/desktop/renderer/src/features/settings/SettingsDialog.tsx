/**
 * AI provider settings — a modal to point the Whiteboard's AI (Billy + Logos)
 * at an endpoint. Reads/writes the CORE's global assistant settings through the
 * Whiteboard backend passthrough. The API key is write-only (blank keeps the
 * stored one). "Test connection" saves the current form, then round-trips a
 * trivial prompt so you can confirm the provider actually responds.
 */

import { useEffect, useRef, useState } from 'react';

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

export function SettingsDialog({ open, baseUrl, writingSettingsApi, onClose }: Props) {
  const [form, setForm] = useState<AiSettings>(EMPTY);
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [test, setTest] = useState<{ ok: boolean; msg: string } | null>(null);
  const firstRef = useRef<HTMLSelectElement>(null);
  const loadedProviderRef = useRef(EMPTY.provider);

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

  // Escape closes; focus the first field.
  useEffect(() => {
    if (!open) return undefined;
    firstRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

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
    <div
      className="cf-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="set-title">
        <div className="settings-head">
          <h2 id="set-title" className="settings-title">
            Settings
          </h2>
          <button type="button" className="settings-close" aria-label="Close settings" onClick={onClose}>
            ×
          </button>
        </div>
        <p className="settings-sub">General writing defaults and the AI connection used by Billy &amp; Logos.</p>

        <h3 className="settings-section-title">Narrative voice</h3>
        <p className="settings-section-note">Used as general guidance by Billy and Logos. Saved immediately on this machine.</p>
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

        <h3 className="settings-section-title">AI provider</h3>
        <p className="settings-section-note">Stored locally. A blank API-key field keeps the saved key for the current provider.</p>

        {loading ? (
          <p className="settings-hint">Loading…</p>
        ) : (
          <div className="settings-form">
            <label className="settings-field">
              <span>Provider</span>
              <select ref={firstRef} value={form.provider} onChange={(e) => selectProvider(e.target.value)}>
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
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
