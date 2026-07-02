# Product Architecture Roadmap

Status: **roadmap / design intent** (documentation only — no code change). Companion
to [ALPHA_RC_STATUS.md](ALPHA_RC_STATUS.md) and the integrity audits.

This document records how the current repository relates to the planned release
products, so the Alpha is frozen with a clear forward path.

---

## 1. Three layers

```
                       ┌─────────────────────────────────────────┐
                       │  Logosforge Python CORE  (this repo)     │
                       │  engine + data model + AI backend        │
                       │  — the reference implementation —        │
                       └───────────────┬─────────────────────────┘
                                       │  (stable, serializable contract /
                                       │   provider + transport seams)
              ┌────────────────────────┼────────────────────────┐
              ▼                                                   ▼
   ┌────────────────────────┐                       ┌────────────────────────┐
   │  Whiteboard            │                        │  Logosforge Pro        │
   │  minimal · "instinct"  │                        │  complete · "architect"│
   │  desktop + web · AI    │                        │  desktop + web · AI    │
   └────────────────────────┘                       └────────────────────────┘
```

1. **Logosforge Core (this repository).** The Python engine + its current Qt UI.
   This is the **reference implementation and conformance oracle** — its behavior
   and its ~1500-test suite define "correct." The Qt UI here is the working
   reference surface, not the shipped commercial UI.
2. **Whiteboard** — a free-tier release product: a **minimal, low-friction,
   AI-powered** writing experience for desktop + web.
3. **Logosforge Pro** — the paid release product: the **complete, AI-powered
   narrative OS** for desktop + web.

Both release products **reuse the same core** and ship **their own UIs** (the
unified/undockable assistant explored earlier belongs in those UIs, not retrofitted
into the Qt reference build).

---

## 2. The two products differ by *posture*, not by "has AI"

**AI is intrinsic to both.** The distinction is how present and how structural the
AI is, and how much of the narrative OS is exposed.

| | **Whiteboard** | **Logosforge Pro** |
|---|---|---|
| Metaphor | **Instinct** | **Architect / planning** |
| Feel | Minimal, calm, gets out of the way | Complete narrative operating system |
| AI posture | **Ambient & unobtrusive** — light-touch suggestions, supports momentum and discovery; the AI *whispers* | **Deep collaborator** — structure, planning, diagnostics, continuity, reflection, controlled rewrite; the AI *co-architects* |
| Surfaces | Curated, gentle subset (write first; help on request) | Full registry + proactive/structural surfaces |
| Audience | Drafting / flow / discovery writers | Planners / structured & long-form / showrunner-style writers |
| Intrusiveness | Low by design | High capability, opt-in depth |

Shared by both: the same engine, the same five writing modes (Novel / Screenplay /
Graphic Novel / Stage Script / Series), the same single AI backend, and the same
**propose-then-confirm** safety model.

---

## 3. Why this is a UI split, not an engine fork

The core is already **UI-agnostic and serializable**, which is what makes "one core,
two products" viable without re-deriving the engine:

- **One shared AI backend** — `logosforge.assistant.chat_completion` +
  `logosforge.providers.build_active_provider`. There is no second chat backend.
- **Injectable seams** — `LogosController(provider_resolver=…, chat_fn=…)` and
  `chat_completion(provider=…)` let any front-end / transport supply its own
  provider wiring without touching the engine.
- **No-Qt logic** — the mode systems (block adapters, planning pipelines,
  diagnostics, reflection, rewrite, continuity, dashboards) are pure logic + DB and
  return dataclasses with `to_dict()`. That is a ready-made, JSON-able API surface.
- **One data model** — `logosforge.db` + `logosforge.story_structure` (canonical
  Act → Chapter → Scene) are shared; there is an (experimental) HTTP API seam that a
  web/Electron client would attach to.

So Whiteboard and Pro are **new UIs over the same core**, attaching through the
serializable contract + the provider/transport seams.

---

## 4. How "instinct vs architect" is implemented (intended)

Tiering and posture are a **capability + presentation profile layered over the
shared action registry**, not a code fork:

- Actions already gate by `writing_mode`. A second axis — a **product/posture
  profile** — selects *which* actions/sections each product exposes and *how
  proactively* the AI surfaces them.
- **Whiteboard** profile: a small, gentle subset; AI is reactive/ambient (help on
  request, minimal structural UI). The core's fast, deterministic checks can power
  unobtrusive in-flow signals; the generative actions stay one tap away.
- **Pro** profile: the full registry, proactive structural surfaces (planning,
  dashboards, continuity, reflection, controlled rewrite).

One engine, two postures — selected by configuration, not by duplicating logic.

---

## 5. Core-as-contract (the one prep that matters most)

For the products to evolve independently while sharing the engine, treat these as
the **versioned public contract** of the core:

1. The `to_dict()` shapes of reports / previews / dashboards (diagnostics,
   reflection, continuity, review, rewrite preview, plan models).
2. The controller / pipeline function signatures (run an action, build a preview,
   apply with confirmation).
3. The provider/chat injection points.
4. The Controlled-Apply gate (preview → confirmed apply; STAGE checkpoint).

Documenting/freezing this contract is the highest-leverage step before building
either UI. The reference Qt build + its test suite act as the conformance oracle.

---

## 6. Invariants every product must preserve

These are non-negotiable across Core, Whiteboard, and Pro:

- **Universal Manuscript** + `writing_mode` adapter; canonical **Act → Chapter →
  Scene** (Series displays Season/Arc · Episode but stores Act · Chapter).
- **Propose-then-confirm** for every mutation; no silent overwrites; mutations flow
  through Controlled Apply.
- **Deterministic vs generative tiers** stay distinct (deterministic checks are
  rule-based and need no provider round-trip; this is an internal capability both
  products can exploit for fast, calm signals — it is *not* a "free = no AI" tier).
- **Mode-gating**, **project isolation**, and **export privacy** (no API keys /
  provider settings / cross-project data / system prompts in any export or report).
- **No-Qt boundary** in core logic modules (UI stays in the UI layer) so the engine
  remains portable to Electron/Web.

---

## 7. Out of scope / deferred (unchanged)

Reserved for later, and explicitly **not** part of the core today:

- ComfyUI / image generation / image prompts / render panels.
- Canvas Plot (hidden/deferred in the reference UI).
- Production scheduling, rehearsal / writers-room management, showrunner automation.
- A separate Season/Episode storage hierarchy (Series stays settings-backed over
  Act → Chapter → Scene).
- Persistent serialized-story relation links (detected/reported, not yet stored).

These remain deferred regardless of product; if any are introduced later, they
belong behind the same propose-then-confirm + privacy invariants.

---

## 8. Sequence (suggested, post-Alpha)

1. **Freeze** this Python core as the reference (done: `0.9.0-alpha`, Alpha gate A).
2. **Document the core contract** (§5) + harden the HTTP API seam (auth) as the
   attach point for web/Electron.
3. **Build the unified AI surface** (one undockable assistant: conversation + a
   mode-aware action palette + inline edits) inside the release UIs.
4. **Whiteboard** first as the minimal/instinct profile; **Logosforge Pro** as the
   complete/architect profile — both consuming the same core via the contract.

This file is design intent only; it changes no behavior in the current build.
