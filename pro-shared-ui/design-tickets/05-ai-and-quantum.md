# Ticket 05 — AI surfaces + Quantum Outliner

> Brief: §4.6, §5. Fills `src/components/ai.tsx` (AssistantDock, ChatPanel,
> CounterpartPanel) + `spatial.tsx` (QuantumOutliner).

## Goal
Four distinct-but-coherent AI presences, all funneling content changes through
the Diff/Impact Confirm modal (Ticket 06). No silent AI — every generative
action is user-invoked.

## Screens / panels
- **Billy (Assistant Dock + Project Chat)** — a docked side assistant and a full
  project-aware chat. Show the active provider; the controlled context that's
  injected (so the user trusts what the AI sees).
- **Logos (inline)** — fast contextual actions (rewrite/expand/explain/connect-to-
  PSYKE…) from the editor's inline bar + command palette + action menus;
  deterministic where possible, confirm-before-apply for edits.
- **Counterpart** — a reflective, **two-stance** feedback panel (never edits).
- **Quantum Outliner** — the signature branching surface: generate **3–5
  narrative branches** from a point, **score** them (show factors), compare on a
  **Quantum Timeline** (canon + active branches in parallel), reframe a scene
  from another POV, flag weak/predictable scenes, then **collapse** to one branch
  (archive the rest). Make it cinematic and high-impact.

## Key interactions
- Chat with context toggles; run a Logos action → preview → confirm; read
  Counterpart's two stances; in Quantum: generate → inspect/score → collapse.

## Data
`AssistantRequestDTO`/`AssistantResponseDTO`, `ConnectorActionDTO[]` (dynamic
Logos/connector actions), `AssistantSettingsDTO` (provider). Quantum branch
state is its own model.

## Acceptance
Billy/Logos/Counterpart/Quantum feel like four tools, one mind; Quantum is a
showpiece; every edit is preview-then-confirm.
