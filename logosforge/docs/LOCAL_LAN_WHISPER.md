# Local LAN Whisper Server (voice MVP — LAN mode)

LAN mode lets LogosForge use **another machine on your trusted local network**
(e.g. a workstation with an RTX GPU) as the Whisper transcription server.
Microphone capture and buffering stay **on your computer**; only finalized audio
segments are uploaded to the server **you** configured. Public cloud is out of
scope: no cloud speech API, no OpenAI Realtime, no public endpoints.

> **LAN mode sends audio only to the configured local network Whisper server.
> Do not use public URLs.** Public IPs/domains, ngrok and cloud-tunnel URLs are
> **blocked** in this Alpha build (`voice_lan_allow_only_private_hosts` is on by
> default and there is no public-URL override). Redirects are refused. Hostnames
> are never DNS-resolved, so a public domain cannot smuggle in a "private" IP.

Allowed addresses: `localhost` / `127.0.0.1` / `::1`, RFC1918 ranges
(`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), IPv4 link-local
(`169.254.0.0/16`) and `.local` mDNS names.

## Option A — companion server (faster-whisper)

A small stdlib HTTP server ships at `scripts/local_whisper_server.py`. It is
**never started or imported by the app** — run it manually on the server
machine:

```bash
pip install faster-whisper

# Same-machine testing (default bind 127.0.0.1, default port 8765):
python scripts/local_whisper_server.py --model /models/faster-whisper-small

# Trusted-LAN serving (EXPLICIT choice — prints a warning):
python scripts/local_whisper_server.py --model /models/faster-whisper-small \
    --host 0.0.0.0 --port 8765
```

Flags: `--model PATH` (prefer a **local model directory** — no downloads on your
behalf) · `--host` (default `127.0.0.1`) · `--port` (default `8765`) ·
`--device auto|cpu|cuda` · `--compute-type auto|int8|float16|int8_float16` ·
`--language` (server default) · `--auth-token TOKEN` ·
`--max-audio-seconds` (60) · `--max-payload-mb` (25) · `--debug` (sizes/timings
only — never audio, transcripts, or tokens).

Endpoints:

- `GET /health` → `{"ok": true, "backend": "faster-whisper", "model_loaded":
  true, "device": "...", "language_default": "auto"}`
- `POST /v1/audio/transcriptions` — OpenAI-compatible local shape: multipart
  `file` (16-bit WAV) + optional `language` / `response_format` (`json` |
  `text`). Returns `{"text": "..."}`.
- `POST /inference` — whisper.cpp-style alias (same handler).

Validation: empty file → 400; payload over the MB cap → 413 (rejected before
the upload is consumed); audio over the seconds cap → 413; non-WAV → 415. If
the model can't load, the server **exits with a clear setup message** — it
never falls back to any cloud service.

**Optional token** (`--auth-token SECRET`): clients must send
`Authorization: Bearer SECRET` (the LogosForge custom header
`X-Voice-Token: SECRET` is also accepted); otherwise 401. This is **basic LAN
protection only — not internet-grade security**. The token is never logged.

> **Security:** binding to a LAN IP / `0.0.0.0` prints: *"LAN mode exposes
> transcription on the local network. Do not expose this port to the public
> internet."* Keep the port inside your trusted LAN and firewall. No tunnels,
> no public URLs, no automatic firewall changes, no admin rights.

## Option B — external whisper.cpp server

Build/install [whisper.cpp](https://github.com/ggerganov/whisper.cpp) separately
(it is **not** vendored in this repo, never compiled by the app, and its models
are never auto-downloaded). Then run its server manually with your local model:

```bash
./server -m /models/ggml-base.en.bin --host 192.168.1.50 --port 8081
```

Desktop settings for whisper.cpp: `voice_lan_api_type = "whisper_cpp"`
(endpoint `/inference`), base URL `http://192.168.1.50:8081`. If your build
uses a different inference path, use `voice_lan_api_type = "custom"` +
`voice_lan_transcription_endpoint`. Same rules: trusted LAN only, firewall the
port, never expose it to the internet, no admin privileges needed.

## Desktop configuration (LogosForge)

1. `enable_voice_mode = true`, backend mode **Local LAN Server**
   (`voice_backend_mode = "lan_server"` — also in the panel's Backend selector).
2. `voice_lan_base_url = "http://<private-lan-ip>:8765"` (companion) or your
   whisper.cpp address.
3. `voice_lan_api_type`: `openai_compatible` (companion default) ·
   `whisper_cpp` · `custom` (+ `voice_lan_transcription_endpoint`).
4. Optional token: `voice_lan_auth_header_name = "Authorization"` +
   `voice_lan_auth_token = "Bearer SECRET"` (or `X-Voice-Token` + `SECRET`).
5. `voice_lan_timeout_seconds` (60), `voice_lan_health_endpoint` (`/health`).
6. Use the panel's **Check LAN server** button, then Start → speak → Stop →
   review → **Commit**.

| key | meaning | default |
|-----|---------|---------|
| `voice_backend_mode` | `"lan_server"` | `"disabled"` |
| `voice_lan_base_url` | e.g. `http://192.168.1.50:8765` | `""` |
| `voice_lan_api_type` | `openai_compatible` · `whisper_cpp` · `custom` | `openai_compatible` |
| `voice_lan_transcription_endpoint` | custom api_type only | `""` |
| `voice_lan_health_endpoint` | health probe path | `/health` |
| `voice_lan_timeout_seconds` | request timeout | `60` |
| `voice_lan_auth_header_name` / `voice_lan_auth_token` | optional static local token (never logged) | `""` |
| `voice_lan_max_audio_seconds` / `voice_lan_max_payload_mb` | refuse oversize segments before sending | `60` / `25` |

## Known limitations

No streaming/WebSocket, no realtime speech-to-speech, no diarization, no voice
commands, no automatic story classification or screenplay formatting, no cloud
realtime, and no model download manager — the model path/name is yours to
provide and manage.

## Troubleshooting

- **"Local LAN Whisper server is not reachable."** — server not running /
  wrong port / firewall. Use the panel's **Check LAN server** button.
- **"LAN Whisper server must be a trusted local network address…"** — the URL
  is public or not parseable as a private address; use a private LAN IP,
  `localhost`, or a `.local` name.
- **HTTP 401** — token mismatch between the server and LogosForge.
- **HTTP 413 / 415** — segment too large/long, or not WAV (the Desktop client
  always sends 16 kHz mono WAV and pre-checks the caps).
