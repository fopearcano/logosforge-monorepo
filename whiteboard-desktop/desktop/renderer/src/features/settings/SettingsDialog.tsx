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
  testAiConnection,
  type AiSettings,
} from './settingsApi';

interface Props {
  open: boolean;
  baseUrl: string;
  onClose: () => void;
}

const EMPTY: AiSettings = { provider: 'LM Studio', model: '', base_url: '', timeout: 0 };

export function SettingsDialog({ open, baseUrl, onClose }: Props) {
  const [form, setForm] = useState<AiSettings>(EMPTY);
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [test, setTest] = useState<{ ok: boolean; msg: string } | null>(null);
  const firstRef = useRef<HTMLSelectElement>(null);

  // Load current settings when opened.
  useEffect(() => {
    if (!open) return undefined;
    setStatus(null);
    setTest(null);
    setApiKey('');
    setLoading(true);
    const ctrl = new AbortController();
    getAiSettings(baseUrl, ctrl.signal)
      .then((s) =>
        setForm({
          provider: s.provider || 'LM Studio',
          model: s.model || '',
          base_url: s.base_url || '',
          timeout: s.timeout || 0,
        }),
      )
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
    setSaving(true);
    setStatus(null);
    try {
      await saveAiSettings(baseUrl, buildPatch());
      setApiKey('');
      setStatus('Saved.');
    } catch {
      setStatus('Save failed.');
    } finally {
      setSaving(false);
    }
  };

  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      await saveAiSettings(baseUrl, buildPatch()); // test what's on screen
      const r = await testAiConnection(baseUrl);
      setTest(
        r.ok
          ? { ok: true, msg: `Connected — ${r.provider} responded.` }
          : { ok: false, msg: r.error || 'No response from the provider.' },
      );
    } catch {
      setTest({ ok: false, msg: 'Test failed.' });
    } finally {
      setTesting(false);
    }
  };

  const busy = saving || loading || testing;

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
            AI provider
          </h2>
          <button type="button" className="settings-close" aria-label="Close settings" onClick={onClose}>
            ×
          </button>
        </div>
        <p className="settings-sub">
          Point the Whiteboard’s AI (Billy &amp; Logos) at your endpoint. Stored locally on this machine.
        </p>

        {loading ? (
          <p className="settings-hint">Loading…</p>
        ) : (
          <div className="settings-form">
            <label className="settings-field">
              <span>Provider</span>
              <select ref={firstRef} value={form.provider} onChange={(e) => set({ provider: e.target.value })}>
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
                placeholder="e.g. llama-3.1-8b · gpt-4o · claude-sonnet-4-5"
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
