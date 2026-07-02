# AI Screenwriting Research Summary

**Scope:** Research extraction only. No code changes, no implementation.
**Audience:** Logosforge / logosforge design — non-novel writing modes
(Screenplay, Graphic Novel, Stage Script, Series). Novel mode is referenced only
where a paper discusses novel → screenplay transformation.

**Papers analyzed**

| ID | arXiv | Short name | Title |
|----|-------|-----------|-------|
| P1 | 2503.15655 | **R²** | *R²: A LLM-Based Novel-to-Screenplay Generation Framework with Causal Plot Graphs* |
| P2 | 2510.23163 | **DSR** | *Beyond Direct Generation: A Decomposed Approach to Well-Crafted Screenwriting with LLMs* |
| P3 | 2602.05854 | **DuoDrama** | *DuoDrama: Supporting Screenplay Refinement Through LLM-Assisted Human Reflection* |

> **Sourcing note.** The PDFs named in the task
> (`2503.15655v1.pdf`, `2510.23163v3.pdf`, `2602.05854v1.pdf`) were **not present**
> in `docs/research/ai_screenwriting/` at the time of analysis. Content below was
> extracted from the corresponding public arXiv records (abstracts + HTML full
> text for P1/P2; abstract + metadata for P3). If the original PDFs are added
> later, this summary should be reconciled against them — figures, exact tables,
> and any appendix-only details may differ. Items derived from the abstract alone
> (most of P3's fine detail) are flagged **[abstract-level]**.

---

## 1. Executive Summary

Across three independent 2025–2026 papers, one architectural conviction recurs:
**well-crafted screenwriting is not a single generation step.** It is a pipeline
of *decomposed* stages — extraction, structuring, narrative drafting, formatting,
and reflective revision — each with a different objective function. Forcing one
model (or one UI surface) to do all of it at once degrades every part.

- **R² (P1)** splits the work into a **Reader** that mines a long source into a
  **causal plot graph** (events + typed, weighted causal edges, made acyclic),
  and a **Rewriter** that traverses that graph to emit scene outlines and then
  scene prose. A cross-cutting **Hallucination-Aware Refinement (HAR)** loop
  keeps every stage grounded in the source. Lesson: *structure causality
  explicitly before you write scenes.*

- **DSR (P2)** splits **creative narrative generation** from **technical
  formatting**. It writes a "screenplay-oriented" novelization first (Stage 1),
  then converts that prose to formatted screenplay (Stage 2). The paper names the
  failure mode of doing both at once the **"Task Coupling Dilemma"** — gradient /
  attention conflict between *creative quality* and *format adherence*. Lesson:
  *outline → rich prose → formatted script; never outline → formatted script.*

- **DuoDrama (P3)** addresses **revision, not generation**. Its **ExReflect**
  workflow has an AI agent first inhabit an **experience role** (react *as* a
  character, from inside) and then switch to an **evaluation role** (critique the
  structure, from outside), producing feedback that provokes *writer reflection*
  rather than autocompleting the script. Lesson: *the highest-value AI surface for
  a real writer is grounded, dual-perspective feedback — not more generated text.*

**The unifying principle for Logosforge:** keep **Outline (structure)**,
**Manuscript (prose)**, and **Export (format)** as genuinely separate stages, and
position the **Assistant / Counterpart / Logos** layer primarily as a *reflective
critic with two stances* (inside-character and outside-structure) rather than as a
one-shot screenplay generator. This is strongly aligned with the current
consolidated architecture (Outline = structure, Manuscript = scene prose,
Export = format) and argues *against* re-coupling them.

---

## 2. Paper-by-Paper Extraction

Each paper is extracted against the ten requested dimensions. Where a paper is
silent on a dimension, that is stated explicitly.

---

### P1 — R²: Novel-to-Screenplay via Causal Plot Graphs

**1. Title & core problem.**
Automating novel → screenplay adaptation with LLMs. Two named obstacles:
(a) **hallucination** — the LLM invents/contradicts plot when extracting from a
long source, producing inconsistent plot lines; (b) **causality extraction** —
screenplays must be ordered by *cause*, not just chronology, and that causal
structure must be recovered from prose.

**2. Main proposed method.**
A **Reader–Rewriter** framework mirroring how a human adapter works:
- **Reader** → extracts events chapter-by-chapter via a **sliding window**, then
  builds a **Causal Plot Graph (CPC)**.
- **Rewriter** → traverses the graph to produce a scene-by-scene **outline**, then
  generates **scene prose**.
- **HAR (Hallucination-Aware Refinement)** runs *inside both* modules as an
  iterative grounding loop. Ablations: removing HAR cost ~38% in grammar/diction
  and ~46% in consistency; removing CPC cost large drops in "interesting" and
  consistency. Reported win-rate gains of **+51.3 / +22.6 / +57.1** absolute over
  ROLLING, Dramatron, and a commercial tool (GPT-4o judge; corroborated by 15
  human evaluators).

**3. Screenplay structure.**
Treats a screenplay as an **interconnected set of scenes**, not a linear chapter
run. Each scene carries: setting (place/time), character goal, and an emotional
arc. Scene *ordering is driven by causality*, not source chronology. The paper
does **not** prescribe act counts or a beat template — structure emerges from the
graph traversal. One of its seven eval axes is explicitly **"Script Format
Compliance."**

**4. Scene generation / refinement.**
Two-step in the Rewriter: (i) **outline generation** — graph traversal yields a
"story core + structure + per-scene writing plan," where each plan = storyline,
goal, place/time, character experiences; (ii) **scene generation** — scene-by-scene,
conditioned on the relevant source chapters *plus previously generated scenes*
for continuity. HAR validates that generated content matches the outlined goal and
stays consistent across scenes.

**5. Causality / plot graph / event dependency.**
The centerpiece. Graph `G = ⟨E, D, W⟩`: **E** = events (place, time, background,
description), **D** = directed causal edges, **W** = edge strength (High/Med/Low).
A **greedy cycle-breaking algorithm** sorts candidate relations by weight + node
degree, adds edges only when they don't create a cycle (reachability test),
yielding a **maximum-strength DAG**. Traversal strategy matters: **Breadth-First**
gave the best coherence/transition/consistency; **Depth-First** was strongest on
"interesting"/creative; chapter-order was the weakest baseline.

**6. Formatting vs. narrative generation.**
Format compliance is *measured* (one of seven axes) but **not architecturally
separated** — R² focuses on getting causal/narrative content right and treats
format as a property of the generated scene. (Contrast with DSR, which makes the
split its thesis.)

**7. Feedback / reflection / revision.**
Revision is **machine-internal** via HAR (self-locate hallucination → retrieve
supporting source context → rewrite → merge → repeat; ~4 rounds optimal, adoption
plateaus ~60%). There is **no human-in-the-loop reflection** surface — this is a
generation system, not a writer-assist system.

**8. Character perspective / internal state.**
Each event/scene plan tracks **character experiences** and goals, and the case
study praises "character development" and "emotional dialogue." But internal state
is captured as *graph/scene metadata to keep characters consistent*, not as an
inhabited first-person perspective (contrast DuoDrama).

**9. Global story coherence.**
Achieved structurally: the acyclic causal graph is the global backbone; BFT
traversal preserves global flow; HAR + "previously generated scenes" context
enforce cross-scene consistency. Coherence is an explicit, separately-scored axis.

**10. Implications for software architecture.**
Validates a **two-stage pipeline with a shared grounding loop**:
*ingest/extract → causal structure → outline → scene prose*, with a refinement
checker that always re-grounds against the source. Maps cleanly onto
Logosforge's **Import/Source → Outline → Manuscript** flow, and suggests a
**typed, weighted, acyclic dependency graph** as the right internal model for
plot/causality (cf. Logosforge's Graph / Timeline links).

---

### P2 — DSR: Decomposed (Dual-Stage) Screenwriting

**1. Title & core problem.**
Direct, end-to-end LLM screenplay generation is "well-crafted" only rarely. Root
cause named the **"Task Coupling Dilemma"**: a single model must *simultaneously*
do **creative narrative construction** and **rigid format adherence**, and these
pull optimization in conflicting directions. Symptoms of coupling: weak thematic
focus, out-of-character dialogue, thin character development.

**2. Main proposed method.**
**Dual-Stage Refinement (DSR):**
- **Stage 1 — Outline → Novel (creative):** a continually-pre-trained model emits
  a **Chain-of-Thought** (exposition strategy, pacing, action, emotion) then a
  **"screenplay-oriented" novelization** — descriptive prose deliberately limited
  to *observable action and audible dialogue*, no internal monologue.
- **Stage 2 — Novel → Screenplay (format):** a *separate* large model, via
  in-context learning, converts the prose to formatted screenplay using a prompt
  that sets a screenwriter persona + explicit formatting rules with examples.

Trained via **hybrid data synthesis** (below). Result: expert score 8.06/12,
**82.7% of human level**, **75% win rate** vs. Gemini-2.5-Pro / Claude-Sonnet-4;
decomposition alone is worth ~+2.4 points over end-to-end.

**3. Screenplay structure.**
"A screenplay differs fundamentally from a novel as a **structured framework for
visual storytelling**." Core requirements an effective model must satisfy:
(1) narrative coherence, (2) character consistency, (3) strict formatting
conventions (scene headings, action lines, dialogue), (4) **performable
dialogue**, (5) **"showing not telling"** — replace exposition with visible action
("He stared at the cracked photograph, his jaw tight, before slowly closing his
eyes" instead of stating an emotion).

**4. Scene generation / refinement.**
Scene drafting happens in **Stage 1 as prose** (richer, easier for an LLM trained
on narrative text), and is *refined into screenplay form* in Stage 2. "Refinement"
here = the staged conversion itself, not an interactive edit loop. Inputs to a
scene: outline `O`, previous context `P`, character profiles `C`, metadata/
directives `M`.

**5. Causality / plot graph / event dependency.**
**Not graph-based.** DSR carries causality/continuity implicitly through the
ordered inputs (previous context `P`, outline `O`) and the CoT "narrative
directives" `Ic` (pacing, emotional trajectory, action choreography, **information-
disclosure strategy**). No explicit DAG (this is R²'s domain).

**6. Formatting vs. narrative generation.**
**This is the paper's thesis.** Coupling the two creates **gradient conflict**;
decoupling "eliminates gradient conflicts and simplifies each optimization
problem." Stage 1 owns *creative quality*; Stage 2 owns *format adherence*. The
intermediate **novel is the bridge representation** — it lets the system exploit
the LLM's strong narrative priors while deferring rigid format to a dedicated step.

**7. Feedback / reflection / revision.**
Evaluation uses a **12-point, six-tier expert rubric** (Unacceptable → Exceptional/
"directly usable") scored by **20+ professional TV screenwriters**, plus error
counts in three buckets: **plot coherence, character development, narrative
pacing**. This is an *assessment* rubric, not an interactive reflection loop — but
the **three error categories and the tiered rubric are directly reusable as a
Logosforge critique schema.**

**8. Character perspective / internal state.**
Deliberately **externalized**: the intermediate novelization is constrained to
"observable on screen and audible as dialogue rather than abstract thoughts and
emotions." Internal state must be *rendered as visible behavior*. (Strong contrast
with DuoDrama, which deliberately re-enters the internal perspective — but for
*feedback*, not for the script body.)

**9. Global story coherence.**
Maintained through ordered inputs (`P`, `O`), CoT narrative directives, and the
hybrid-synthesis training that keeps **input–output alignment** tight (low
variance 0.14; "minimal deviation from the input outline"). Reverse-only data
synthesis hurt coherence via input–output misalignment; **hybrid** (reverse-
compress inputs + forward-generate targets from a teacher) fixed it.

**10. Implications for software architecture.**
The cleanest mandate for Logosforge: **Outline → (rich narrative) → Export are
distinct stages and must stay distinct.** Specifically:
- **Assistant/Outline** should produce *structure + intent* (outline, character
  profiles, directives), not formatted script.
- **Manuscript** is the *creative prose* stage (screenplay-oriented description:
  observable action + performable dialogue).
- **Export** is the *format* stage (scene headings/action/dialogue conventions),
  ideally driven by explicit rules + examples, kept separate from drafting.
- Generation that jumps **outline → formatted screenplay** in one shot should be
  treated as a known anti-pattern.

---

### P3 — DuoDrama: Refinement via LLM-Assisted Human Reflection  *(CHI 2026)*

> Most fine detail below is **[abstract-level]** (abstract + metadata only). Treat
> exact mechanisms as directional until reconciled with the full PDF.

**1. Title & core problem.**
Existing AI screenwriting tools push *generation*; they under-serve **revision**.
DuoDrama targets the gap: helping a professional writer **reflect** on a draft
along two axes — **character perspective** (inside) and **narrative structure**
(outside) — rather than handing them more autogenerated text. **[abstract-level]**

**2. Main proposed method.**
**ExReflect — Experience-Grounded Feedback Generation Workflow.** An AI agent runs
two stances in sequence:
- **Experience role** — adopts a character's viewpoint and **generates that
  character's in-situ reactions/experience** to the scene.
- **Evaluation role** — *then* switches to a critic and produces feedback
  **grounded in those generated experiences**.
Design informed by a **formative study with 9 professional screenwriters**;
evaluated with **14 professional screenwriters**, showing gains in *feedback
quality, alignment, and depth of writer reflection*. **[abstract-level]**

**3. Screenplay structure.**
Engages structure as one of the **two feedback axes** ("narrative structure"),
i.e., structure is something the *evaluation role critiques*, not something the
system generates. No explicit act/beat schema is specified at abstract level.
**[abstract-level]**

**4. Scene generation / refinement.**
Refinement is **human-led, AI-supported**: the AI does not rewrite the scene; it
produces *reflective feedback* that the writer acts on. The unit of work is the
**writer's revision pass**, with the AI as a structured mirror. **[abstract-level]**

**5. Causality / plot graph / event dependency.**
Not a focus (HCI/reflection paper, category cs.HC). No plot-graph machinery.
**[abstract-level]**

**6. Formatting vs. narrative generation.**
Out of scope — DuoDrama operates on an existing draft and concerns **feedback**,
not formatting or first-draft narrative generation. **[abstract-level]**

**7. Feedback / reflection / revision.**
**The entire contribution.** Key idea: feedback is more useful when it is
**experience-grounded** — derived from first simulating *what a character would
feel/do*, then evaluating against that. Measured improvements in *feedback
quality* and in the *depth of the writer's own reflection*. This is the strongest
external evidence in the three papers for a **reflective-critic** AI surface over
an autocomplete one. **[abstract-level]**

**8. Character perspective / internal state.**
Central and explicit: the **experience role inhabits the character's internal
state** to ground the critique. Note the productive tension with DSR — DSR keeps
internal state *out* of the script body (show, don't tell), while DuoDrama
deliberately *re-enters* internal state to *generate feedback about* the draft.
The two are compatible: internal perspective is a **lens for critique**, not
content for the manuscript. **[abstract-level]**

**9. Global story coherence.**
Approached via the **evaluation (outside) role**, which critiques narrative
structure / coherence as one of its two axes — again as feedback to the human, not
as an automatic global rewrite. **[abstract-level]**

**10. Implications for software architecture.**
Argues for a **two-stance reflective assistant**:
- a **"Counterpart"/experience stance** that role-plays a character from the
  inside to surface emotional/motivational gaps, and
- a **"Logos"/evaluation stance** that critiques structure/coherence from the
  outside,
with the AI's output framed as **prompts for the writer's reflection**, kept
distinct from any generate-into-the-manuscript action. **[abstract-level]**

---

## 3. Cross-Paper Principles

1. **Decompose the pipeline; never collapse it.**
   R² splits Reader/Rewriter; DSR splits creative/format; DuoDrama splits
   generation/reflection (and experience/evaluation). All three find that the
   *separation itself* is where quality comes from. DSR even quantifies it
   (~+2.4 points from decomposition alone).

2. **An intermediate representation beats a direct jump.**
   R² → causal plot graph; DSR → screenplay-oriented novelization. A purpose-built
   middle layer (structure, or rich prose) is what makes the final screenplay good.

3. **Causality, not chronology, orders scenes.** (R², echoed by DSR's
   "information-disclosure strategy" directive.) Typed, weighted, **acyclic**
   dependencies are a first-class object.

4. **Format adherence is a *separate* objective from narrative quality.** (DSR
   thesis; R² measures format as its own axis.) Conflating them degrades both.

5. **"Show, don't tell" is an explicit, enforceable constraint.** (DSR) The script
   body should hold *observable action + performable dialogue*; internal monologue
   is excluded from the body.

6. **Internal character perspective belongs in the *critique/feedback* layer.**
   (DuoDrama experience role) Inhabiting a character is high-value for *evaluating*
   a draft, even though it's excluded from the *body* of the script.

7. **Grounding loops prevent drift.** R²'s HAR (re-ground to source) and DSR's
   hybrid synthesis (keep input–output aligned) both fight hallucination/deviation
   by *always re-checking against an anchor*.

8. **The most valuable human-facing AI is reflective, not generative.**
   (DuoDrama, validated with 14 pros) Feedback that deepens the writer's own
   thinking beats more autogenerated pages.

9. **Evaluation rubrics are reusable design specs.** DSR's three error buckets
   (**plot coherence, character development, pacing**) + tiered quality ladder, and
   R²'s seven axes (interesting, coherent, human-like, diction/grammar, transition,
   **format compliance**, consistency) are ready-made critique schemas.

10. **Scene = goal + setting + character experience + emotional arc.** (R² scene
    plan; DSR character profiles + directives) A scene is a structured object, not
    a free-text blob.

---

## 4. Implications for Logosforge

> Design implications only. **No code changes proposed here.** These map findings
> onto existing surfaces (Outline / Manuscript / Export / Assistant / Counterpart /
> Logos / Graph / Timeline) for the non-novel modes.

**4.1 Validates the current consolidated separation.**
The recent consolidation — **Outline = structure (Act→Chapter→Scene)**,
**Manuscript = scene prose**, **Export = format** — is exactly the decomposition
DSR proves and R² embodies. *This research is a reason to keep them separate, not
to re-couple.* It also reinforces the existing rule that **outline generation must
never write manuscript body** (DSR's "show, don't tell" + R²'s outline-then-prose).

**4.2 Outline as structure + intent (not script).**
R²/DSR suggest the Outline layer should carry, per scene: **goal, place/time,
character experiences/profiles, emotional arc, and "directives"** (pacing,
information-disclosure). Logosforge's Scene already has `summary`, `act`,
`chapter`, `plotline` — these are the right hooks; the research argues for keeping
*intent* metadata in planning rows and *prose* in `content`.

**4.3 Manuscript = "screenplay-oriented" prose for non-novel modes.**
DSR's constraint (observable action + performable dialogue, no internal monologue
in the body) is a precise, testable style spec for **Screenplay / Stage Script /
Series** manuscripts — and a natural fit for **Graphic Novel** (panels are
inherently "what is seen"). Internal state → externalize as visible behavior.

**4.4 Export = dedicated format stage.**
DSR Stage 2 (persona + explicit formatting rules + examples, applied *after*
drafting) mirrors Logosforge's **Export / ScreenplayMode / ProfessionalScreenplay
Output**. The research endorses keeping formatting rules in Export, driven by
explicit rule+example prompts, decoupled from drafting.

**4.5 Assistant / Counterpart / Logos as a two-stance reflective critic.**
DuoDrama's **experience role** ↔ **Counterpart** (inhabit a character, surface
motivation/emotion gaps) and **evaluation role** ↔ **Logos** (critique structure/
coherence). The strongest takeaway: **frame these as feedback that provokes writer
reflection, not as one-click rewrites.** This aligns with the existing guard that
**Assistant Outline-mode is feedback/structure, not free manuscript injection.**

**4.6 Graph / Timeline as the causal backbone.**
R²'s typed, weighted, **acyclic** causal graph is a strong model for Logosforge's
**Narrative Knowledge Graph / Timeline links** (which already have typed links and
ordering). The cycle-breaking + BFT-for-coherence findings are concrete guidance
if causal ordering is ever surfaced.

**4.7 Reusable critique schema (no new agents needed).**
DSR's error buckets (**plot coherence / character development / pacing**) and R²'s
seven axes (incl. **format compliance, consistency**) can inform existing
Continuity / Narrative Health reporting without adding AI systems — they're
checklists, not models.

---

## 5. Open Questions

1. **PDF reconciliation.** The named PDFs weren't in the repo; P3's detail is
   abstract-level. Add the PDFs and reconcile exact mechanisms/tables, especially
   DuoDrama's ExReflect steps and UI.
2. **Causal graph vs. existing Graph/Timeline.** Does R²'s typed-weighted-DAG add
   anything over Logosforge's current link model, or is it already covered?
3. **"Directives" metadata.** DSR's pacing / information-disclosure directives have
   no obvious home today — planning metadata vs. Assistant context vs. nothing?
4. **Show-don't-tell enforcement.** Could DSR's body constraint become a Continuity
   check for non-novel modes — and would that be helpful or annoying to writers?
5. **Reflective vs. generative Assistant.** DuoDrama says reflection wins for pros;
   how far should Counterpart/Logos lean reflective vs. generative, per mode?
6. **Graphic Novel / Stage Script fit.** All three papers center film/TV
   screenplay; how much transfers to panel-based (Graphic Novel) and
   stage-direction-heavy (Stage Script) forms?
7. **Evaluation, not just generation.** Worth adopting a DSR-style tiered rubric
   internally to *measure* output quality across modes?

---

## 6. Concepts to Compare Against Logosforge Code

> A checklist for a *future* read-through (no audit performed here).

| Research concept | Likely Logosforge counterpart | Question to verify |
|---|---|---|
| R² Reader/Rewriter split | Import/Source → Outline → Manuscript | Is extraction→structure→prose actually staged, or short-circuited? |
| R² causal plot graph (typed/weighted DAG) | Narrative Knowledge Graph; Timeline links (`TimelineLink`, `TIMELINE_LINK_TYPES`) | Are links typed/weighted? Acyclic guarantees anywhere? |
| R² scene plan (goal/place/time/experience) | `Scene.summary` / `act` / `chapter` / `plotline` | Are intent fields distinct from prose `content`? |
| R² HAR grounding loop | Continuity engine; manuscript_repair; outline repair/validate | Do we re-ground generated content against a source anchor? |
| DSR creative/format split | Outline / Manuscript vs. Export / ScreenplayMode | Is any path doing outline→formatted-script in one jump? |
| DSR intermediate novelization | Manuscript prose stage | For non-novel modes, is the body "observable action + performable dialogue"? |
| DSR "show, don't tell" body constraint | WritingModes; Continuity checks | Any rule keeping internal monologue out of script bodies? |
| DSR error buckets (coherence/character/pacing) | NarrativeHealth; Continuity report | Do reports map to these three? |
| DSR tiered quality rubric | (none?) | Is there any internal quality scoring? |
| DuoDrama experience role (inside) | Counterpart | Can Counterpart role-play a character from the inside for feedback? |
| DuoDrama evaluation role (outside) | Logos | Does Logos critique structure/coherence as feedback (not rewrite)? |
| DuoDrama reflection-first stance | Assistant Outline-mode guards | Is Assistant framed as reflective feedback vs. body injection? |
| R² seven eval axes (incl. format compliance) | Continuity / Export validation | Is screenplay format compliance checked anywhere? |

---

*End of research summary. No code was modified; no features were implemented.*
