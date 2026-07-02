# AI Setup (Alpha)

Logosforge uses **one shared AI provider** at a time, configured in **Assistant →
Settings**. The same setting drives the Assistant, Logos, Quantum and the API. No
provider is required to use the editor — only AI features need one.

Settings persist locally; the **API key is masked in the UI, never logged, and
never written to project files or exports**.

## Supported providers

| Provider | Key | Default endpoint | Notes |
|----------|-----|------------------|-------|
| **LM Studio** | none | `http://localhost:1234/v1` | local; start the LM Studio server first |
| **Ollama** | none | `http://localhost:11434/v1` | local; `ollama serve` + pull a model |
| **OpenAI** | required | `https://api.openai.com/v1` | env fallback `OPENAI_API_KEY` |
| **Anthropic** | required | `https://api.anthropic.com` | env fallback `ANTHROPIC_API_KEY` |
| **OpenRouter** | required | `https://openrouter.ai/api/v1` | env fallback `OPENROUTER_API_KEY` |

In Settings: pick the **Provider**, set the **Model** (you can type a **custom
model name**), the **Base URL** (for local servers / custom hosts), and the **API
key** (only shown when the provider needs one).

## LM Studio (local)

1. Install LM Studio, download a chat model.
2. Start its **local server** (default `http://localhost:1234/v1`).
3. In Logosforge: Provider = **LM Studio**, Base URL = the server URL, Model =
   the loaded model name (or leave blank for the server default).

## Ollama (local)

1. Install Ollama; `ollama pull llama3.1` (or any model).
2. Ensure `ollama serve` is running.
3. Provider = **Ollama**, Base URL = `http://localhost:11434/v1`, Model =
   e.g. `llama3.1`.

## OpenAI

Provider = **OpenAI**, paste your `sk-…` key, choose a model (e.g. `gpt-4.1`,
`gpt-4o`, `o3`). Or set `OPENAI_API_KEY` in the environment.

## Anthropic

Provider = **Anthropic**, paste your key, choose a model (e.g.
`claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`). Or set
`ANTHROPIC_API_KEY`.

## OpenRouter

Provider = **OpenRouter**, paste your key, pick a routed model (e.g.
`openrouter/auto`, `anthropic/claude-opus-4-8`, `openai/gpt-4.1`). Or set
`OPENROUTER_API_KEY`.

## Timeout settings

- Set **API timeout** (seconds) in Assistant Settings. `0` = use the per-provider
  default.
- Defaults: **local = 300s**, **cloud = 120s** (local models are slower).
- If a slow local model times out, **increase the timeout** here.

## Common errors

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| "… timed out after Ns" | model too slow / not loaded | increase timeout; load/start the model/server |
| "… requires an API key" | missing key for OpenAI/Anthropic/OpenRouter | paste the key in Settings (or set the env var) |
| "Base URL is required" | empty endpoint | set the Base URL |
| connection refused | local server not running | start LM Studio / `ollama serve` |
| HTTP 401 / 403 | wrong/expired key | re-paste the key |
| HTTP 404 model | model name not on the server | type the exact model id |

See also **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.
