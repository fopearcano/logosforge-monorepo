/** Frontend API client for the global AI provider settings (not doc-scoped). */

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export const AI_PROVIDERS = ['LM Studio', 'Ollama', 'OpenAI', 'Anthropic'] as const;

/** Default base URL per provider (used by the "Default" button in the dialog). */
export const PROVIDER_DEFAULT_URL: Record<string, string> = {
  'LM Studio': 'http://localhost:1234/v1',
  Ollama: 'http://localhost:11434/v1',
  OpenAI: 'https://api.openai.com/v1',
  Anthropic: 'https://api.anthropic.com',
};

export interface AiSettings {
  provider: string;
  model: string;
  base_url: string;
  timeout: number;
  api_key?: string | null; // write-only; never returned by GET
}

export interface AiTestResult {
  ok: boolean;
  provider: string;
  reply?: string | null;
  error?: string | null;
}

export async function getAiSettings(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<AiSettings> {
  const res = await fetch(`${baseUrl}/api/settings/ai`, { signal });
  if (!res.ok) throw new Error(`Request failed (HTTP ${res.status})`);
  return (await res.json()) as AiSettings;
}

export async function saveAiSettings(
  baseUrl: string = DEFAULT_BASE_URL,
  patch: Partial<AiSettings>,
): Promise<AiSettings> {
  const res = await fetch(`${baseUrl}/api/settings/ai`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`Save failed (HTTP ${res.status})`);
  return (await res.json()) as AiSettings;
}

export async function testAiConnection(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<AiTestResult> {
  const res = await fetch(`${baseUrl}/api/settings/ai/test`, { method: 'POST', signal });
  if (!res.ok) throw new Error(`Test failed (HTTP ${res.status})`);
  return (await res.json()) as AiTestResult;
}
