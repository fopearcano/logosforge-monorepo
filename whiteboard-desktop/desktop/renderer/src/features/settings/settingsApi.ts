/** Frontend API client for the global AI provider settings (not doc-scoped). */

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export const AI_PROVIDERS = ['LM Studio', 'Ollama', 'OpenAI', 'Anthropic', 'OpenRouter'] as const;

/** Default base URL per provider (used by the "Default" button in the dialog). */
export const PROVIDER_DEFAULT_URL: Record<string, string> = {
  'LM Studio': 'http://localhost:1234/v1',
  Ollama: 'http://localhost:11434/v1',
  OpenAI: 'https://api.openai.com/v1',
  Anthropic: 'https://api.anthropic.com',
  // OpenRouter is OpenAI-compatible — the core routes it through the OpenAI path
  // (chat/completions + Bearer key); models are namespaced e.g. anthropic/claude-*.
  OpenRouter: 'https://openrouter.ai/api/v1',
};

export const PROVIDERS_REQUIRING_API_KEY = new Set(['OpenAI', 'Anthropic', 'OpenRouter']);

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

/** Provider-specific URL/model/key state cannot safely carry across providers. */
export function settingsAfterProviderChange(current: AiSettings, provider: string): AiSettings {
  return {
    ...current,
    provider,
    base_url: PROVIDER_DEFAULT_URL[provider] || '',
    model: '',
  };
}

/** Client-side preflight for failures we can explain before making a 502 request. */
export function validateAiSettings(
  form: AiSettings,
  apiKey: string,
  loadedProvider: string,
): string | null {
  if (!form.base_url.trim()) return 'Enter a Base URL (or click Default).';
  if (form.provider !== 'LM Studio' && !form.model.trim()) {
    return `Enter a model for ${form.provider}.`;
  }
  const switched = form.provider !== loadedProvider;
  if (switched && PROVIDERS_REQUIRING_API_KEY.has(form.provider) && !apiKey.trim()) {
    return `Enter the ${form.provider} API key after switching providers.`;
  }
  return null;
}

async function responseError(res: Response, fallback: string): Promise<Error> {
  try {
    const data = (await res.json()) as {
      detail?: string;
      error?: string | { message?: string };
    };
    const message =
      (typeof data.error === 'object' ? data.error?.message : data.error) || data.detail;
    if (message) return new Error(message);
  } catch {
    /* fall through to the stable HTTP fallback */
  }
  return new Error(`${fallback} (HTTP ${res.status})`);
}

export async function getAiSettings(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<AiSettings> {
  const res = await fetch(`${baseUrl}/api/settings/ai`, { signal });
  if (!res.ok) throw await responseError(res, 'Couldn’t load AI settings');
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
  if (!res.ok) throw await responseError(res, 'Couldn’t save AI settings');
  return (await res.json()) as AiSettings;
}

export async function testAiConnection(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<AiTestResult> {
  const res = await fetch(`${baseUrl}/api/settings/ai/test`, { method: 'POST', signal });
  if (!res.ok) throw await responseError(res, 'AI connection test failed');
  return (await res.json()) as AiTestResult;
}
