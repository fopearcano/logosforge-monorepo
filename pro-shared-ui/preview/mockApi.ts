import type {
  ApiClient,
  NoteDTO,
  CharacterDTO,
  CharacterUpdateDTO,
  ProjectDTO,
  SceneDTO,
  OutlineNodeDTO,
  PsykeEntryDTO,
  PsykeRelationDTO,
  PsykeProgressionDTO,
  TimelineEventDTO,
  PlotBlockDTO,
  PlotSceneDTO,
  ExportRequestDTO,
  ExportResponseDTO,
} from "@logosforge/ui-contracts";

const delay = (ms = 280) => new Promise<void>((r) => setTimeout(r, ms));

// ── "Null Horizon" sample data — the same story the rest of the demo tells. ──

const PROJECTS: ProjectDTO[] = [
  { id: 1, title: "Null Horizon", description: "Screenplay · Feature", narrative_engine: "screenplay", default_writing_format: "screenplay", format_mode: "screenplay" },
  { id: 2, title: "Salt Flats", description: "Novel · Prose", narrative_engine: "novel", default_writing_format: "novel", format_mode: "novel" },
  { id: 3, title: "The Quiet Fleet", description: "Series · Teleplay", narrative_engine: "series", default_writing_format: "series", format_mode: "series" },
];

const scene = (s: Partial<SceneDTO>): SceneDTO => ({
  id: 0, title: "", summary: "", synopsis: "", goal: "", conflict: "", outcome: "", beat: "", act: "",
  chapter: "", plotline: "", color_label: "", tags: [], content: "", sort_order: 0, order_index: 0,
  character_ids: [], place_ids: [], ...s,
});

const SCENES: SceneDTO[] = [
  scene({ id: 1, title: "Cold Open", summary: "Marlow wakes the station. The planet is already wrong.", act: "ACT I", chapter: "1.1", beat: "Opening Image", content: "The corridor breathes...", sort_order: 1, tags: ["dawn"] }),
  scene({ id: 2, title: "Distress Loop", summary: "A 9-year-old signal repeats. Vesper recognizes the voice.", act: "ACT I", chapter: "1.2", beat: "Catalyst", content: "A hatch cycles.", sort_order: 2, tags: ["setup"] }),
  scene({ id: 3, title: "The Black Box", summary: "A sealed unit is logged, then never opened.", act: "ACT I", chapter: "1.3", beat: "Debate", sort_order: 3, tags: ["setup"] }),
  scene({ id: 12, title: "Observation Ring", summary: "Marlow and Vesper, the static, the Warden's count.", act: "ACT II", chapter: "2.4", beat: "Midpoint", content: "INT. HELIOS-9 — NIGHT...", sort_order: 12, tags: ["dialogue"] }),
  scene({ id: 14, title: "The Confession", summary: "Three exposition scenes in a row — tension flattens.", act: "ACT II", chapter: "2.5", beat: "Bad Guys Close In", sort_order: 14 }),
  scene({ id: 21, title: "All Is Lost", summary: "The reactor goes quiet. So does Vesper.", act: "ACT II", chapter: "2.7", beat: "All Is Lost", sort_order: 21, tags: ["climax"] }),
  scene({ id: 22, title: "Break Into Three", summary: "Marlow opens the box.", act: "ACT III", chapter: "3.1", beat: "Break Into Three", sort_order: 22 }),
];

const node = (id: number, parent_id: number | null, title: string, description: string, sort_order: number, children: OutlineNodeDTO[] = []): OutlineNodeDTO =>
  ({ id, parent_id, title, description, sort_order, children });

const OUTLINE: OutlineNodeDTO[] = [
  node(1, null, "ACT I", "Arrival on a dead station.", 0, [
    node(2, 1, "Chapter 1.1 · Arrival", "", 0, [
      node(3, 2, "Cold Open", "Marlow wakes the station. The planet is already wrong.", 0),
      node(4, 2, "Boot Sequence", "Systems come up one by one.", 1),
    ]),
    node(5, 1, "Chapter 1.2 · The Signal", "", 1, [
      node(6, 5, "Distress Loop", "A 9-year-old signal repeats.", 0),
    ]),
  ]),
  node(7, null, "ACT II", "The Warden tightens its grip.", 1, [
    node(8, 7, "Chapter 2.4 · Convergence", "", 0, [
      node(9, 8, "Observation Ring", "Marlow + Vesper. The static. The count.", 0),
    ]),
  ]),
  node(10, null, "ACT III", "Open the box.", 2, []),
];

// async-extraction mock jobs — getExtractJob ticks progress per poll for a visible bar
const MOCK_EXTRACT_JOBS: Record<string, { done: number; total: number; result: unknown }> = {};
let MOCK_EXTRACT_SEQ = 0;

// format-data authoring mock store (create-append + list)
let MOCK_FD_SEQ = 100;
const MOCK_GN_PAGES: Record<string, unknown>[] = [{ id: 1, page_number: 1, summary: "The vault at night", reveal_type: "", splash_page: false }];
const MOCK_GN_PANELS: Record<string, unknown>[] = [{ id: 2, page_id: 1, panel_number: 1, description: "Mara enters the dark", visual_motifs: ["silence"] }];
const MOCK_STAGE_CUES: Record<string, unknown>[] = [];
const MOCK_STAGE_ENTR: Record<string, unknown>[] = [];
const MOCK_STAGE_BIZ: Record<string, unknown>[] = [];
const MOCK_SEASONS: Record<string, unknown>[] = [{ id: 1, season_number: 1, title: "Descent" }];
const MOCK_EPISODES: Record<string, unknown>[] = [];
const MOCK_ARCS: Record<string, unknown>[] = [];
const MOCK_PLOTLINES: Record<string, unknown>[] = [];
const MOCK_SERIES_MEM: Record<number, { entry_id: number; continuity_flags: string; current_status_by_episode: Record<string, string> }> = {};
const MOCK_CONTINUITY: Record<number, Record<string, unknown>[]> = {};
const MOCK_GN_ITEMS: Record<string, unknown>[] = [];
const MOCK_GN_APPEAR: Record<string, unknown>[] = [];

const PSYKE: PsykeEntryDTO[] = [
  { id: 1, name: "MARLOW", type: "character", aliases: [], notes: "Ex-flight engineer. Carries the Kessler burn.", is_global: false, details: { role: "Protagonist" } },
  { id: 2, name: "VESPER", type: "character", aliases: ["Vess", "the Confidant"], notes: "Speaks in understatement; deflects with logistics.", is_global: true, details: { role: "Deuteragonist", want: "To be forgiven for the relay order she signed.", need: "To forgive herself.", lie: "Silence keeps people safe.", wound: "She stranded the Kessler crew." } },
  { id: 3, name: "THE WARDEN", type: "character", aliases: [], notes: "The thing they no longer call a person.", is_global: false, details: { role: "Antagonist" } },
  { id: 4, name: "HELIOS-9", type: "place", aliases: [], notes: "The station.", is_global: true, details: {} },
  { id: 5, name: "THE BLACK BOX", type: "object", aliases: [], notes: "Sealed unit, never opened.", is_global: false, details: {} },
  { id: 6, name: "STATIC", type: "theme", aliases: [], notes: "Grief motif.", is_global: false, details: {} },
];

const RELATIONS: PsykeRelationDTO[] = [
  { id: "1:2", source_id: 1, target_id: 2, source: "MARLOW", target: "VESPER", relation_type: "confides" },
  { id: "2:3", source_id: 2, target_id: 3, source: "VESPER", target: "THE WARDEN", relation_type: "deceives" },
];

const PROGRESSIONS: PsykeProgressionDTO[] = [
  { id: 1, entry_id: 2, text: "Recognizes the looping voice.", scene_id: 2, scene_title: "Distress Loop", sort_order: 0 },
  { id: 2, entry_id: 2, text: "Confesses, but only half of it.", scene_id: 12, scene_title: "Observation Ring", sort_order: 1 },
  { id: 3, entry_id: 2, text: "Goes silent. Pays off the motif.", scene_id: 21, scene_title: "All Is Lost", sort_order: 2 },
];

const tEvent = (e: Partial<TimelineEventDTO>): TimelineEventDTO => ({
  id: 0, order_index: 0, title: "", act: "", chapter: "", time_of_day: "", location: "", duration_minutes: 0, character_states: [], ...e,
});

const TIMELINE: TimelineEventDTO[] = [
  tEvent({ id: 1, order_index: 1, title: "Cold Open", act: "ACT I", chapter: "1.1", time_of_day: "DAWN", location: "Helios-9 · corridor", duration_minutes: 3, character_states: [{ character: "MARLOW", state: "alone, waking" }] }),
  tEvent({ id: 2, order_index: 2, title: "Distress Loop", act: "ACT I", chapter: "1.2", time_of_day: "DAY", location: "Comms", duration_minutes: 5, character_states: [{ character: "VESPER", state: "recognizes the voice" }] }),
  tEvent({ id: 12, order_index: 5, title: "Observation Ring", act: "ACT II", chapter: "2.4", time_of_day: "NIGHT", location: "Observation deck", duration_minutes: 8, character_states: [{ character: "MARLOW", state: "pressing" }, { character: "VESPER", state: "deflecting" }] }),
  tEvent({ id: 14, order_index: 6, title: "The Confession", act: "ACT II", chapter: "2.5", character_states: [{ character: "VESPER", state: "half-truth" }] }),
  tEvent({ id: 21, order_index: 9, title: "All Is Lost", act: "ACT II", chapter: "2.7", time_of_day: "NIGHT", location: "Reactor", character_states: [{ character: "VESPER", state: "goes silent" }, { character: "THE WARDEN", state: "counts" }] }),
  tEvent({ id: 22, order_index: 10, title: "Break Into Three", act: "ACT III", chapter: "3.1", character_states: [{ character: "MARLOW", state: "opens the box" }] }),
];

const pScene = (s: Partial<PlotSceneDTO>): PlotSceneDTO => ({ scene_id: null, title: "", act: "", summary: "", beat: "", color_label: "", order_index: 0, ...s });

const PLOT: PlotBlockDTO[] = [
  { id: "main", plotline: "MAIN · Marlow", scenes: [
    pScene({ scene_id: 1, title: "Cold Open", act: "ACT I", beat: "Opening Image", summary: "Marlow wakes the station.", order_index: 1, color_label: "#4cc2ff" }),
    pScene({ scene_id: 12, title: "Observation Ring", act: "ACT II", beat: "Midpoint", summary: "Marlow + Vesper. The static.", order_index: 5, color_label: "#4cc2ff" }),
    pScene({ scene_id: 22, title: "Break Into Three", act: "ACT III", beat: "Break Into Three", summary: "Marlow opens the box.", order_index: 10, color_label: "#4cc2ff" }),
  ] },
  { id: "vesper", plotline: "SUBPLOT · Vesper", scenes: [
    pScene({ scene_id: 2, title: "Distress Loop", act: "ACT I", beat: "Catalyst", summary: "Vesper knows the voice.", order_index: 2, color_label: "#62d99a" }),
    pScene({ scene_id: 21, title: "All Is Lost", act: "ACT II", beat: "All Is Lost", summary: "So does Vesper.", order_index: 9, color_label: "#62d99a" }),
  ] },
  { id: "warden", plotline: "THREAT · Warden", scenes: [
    pScene({ scene_id: 99, title: "The Count", act: "ACT II", beat: "Bad Guys Close In", summary: "The Warden counts down.", order_index: 7, color_label: "#e8443a" }),
  ] },
];

// mutable so the mock persists toggles within a session (project settings bag)
let SETTINGS: Record<string, unknown> = {
  focus_mode: false,
  typewriter_mode: false,
  writing_language_code: "en",
  current_language: "en",
  chat_opacity: 92,
  chat_bg_color: "#3a2a55",
  chat_text_color: "#ffb000",
};

const NOTES: NoteDTO[] = [
  { id: 1, title: "The Warden Rules", content: "No one says its name. It speaks only in counts. Never show its face before Act III.", tags: [], pinned: true, psyke_links: [3], scene_links: [21] },
  { id: 2, title: "Static = grief motif", content: "The interference grows louder near loss. Pay it off when Vesper goes quiet.", tags: ["theme"], pinned: false, psyke_links: [], scene_links: [] },
  { id: 3, title: "Kessler burn — backstory", content: "What Marlow did at the relay. Drip it; never a full flashback.", tags: ["backstory"], pinned: false, psyke_links: [1, 4], scene_links: [] },
  { id: 4, title: "Open the box?", content: "Decide before draft 2: does the black box pay off as device or as choice?", tags: [], pinned: false, psyke_links: [5], scene_links: [4] },
  { id: 5, title: "Cold-open candidates", content: "Either the distress loop or the dead-planet drift. Lean drift — quieter, lonelier.", tags: ["structure"], pinned: false, psyke_links: [], scene_links: [1] },
];

/**
 * Minimal mock of the logosforge core ApiClient for the preview. Returns the
 * sample data for the wired domains; the brief delay makes loading states visible.
 */
const MOCK_CHARACTERS: CharacterDTO[] = [
  { id: 1, name: "MARLOW", description: "", color: "#4cc2ff", psyke_entry_id: null },
  { id: 2, name: "VESPER", description: "", color: "#f5b133", psyke_entry_id: null },
];

// In-session scene-tags per theme entry id (mock seeds the STATIC theme, id 6).
const MOCK_THEME_SCENES: Record<number, number[]> = { 6: [1, 3] };

export function createMockApiClient(): ApiClient {
  return {
    async listNotes() { await delay(); return NOTES.map((n) => ({ ...n })); },
    async listCharacters() { await delay(); return MOCK_CHARACTERS.map((c) => ({ ...c })); },
    async updateCharacter(_p: number, characterId: number, body: CharacterUpdateDTO) {
      await delay();
      const c = MOCK_CHARACTERS.find((x) => x.id === characterId);
      if (!c) throw new Error(`character ${characterId} not found`);
      if (body.name !== undefined) c.name = body.name;
      if (body.description !== undefined) c.description = body.description;
      if ("psyke_entry_id" in body) c.psyke_entry_id = body.psyke_entry_id ?? null;
      return { ...c };
    },
    async backfillCharacterLinks() { await delay(); return { ok: true, linked: 0 }; },
    async getThemeScenes(_p: number, entryId: number) { await delay(140); return { entry_id: entryId, scene_ids: [...(MOCK_THEME_SCENES[entryId] ?? [])] }; },
    async setThemeScenes(_p: number, entryId: number, sceneIds: number[]) { await delay(160); MOCK_THEME_SCENES[entryId] = [...sceneIds]; return { entry_id: entryId, scene_ids: [...sceneIds] }; },
    async listProjects() { await delay(); return PROJECTS.map((p) => ({ ...p })); },
    async listScenes() { await delay(); return SCENES.map((s) => ({ ...s })); },
    async updateScene(_p: number, sceneId: number, patch: Record<string, unknown>) {
      await delay(120);
      const s = SCENES.find((x) => x.id === sceneId);
      if (!s) return { id: sceneId } as unknown as SceneDTO;
      // mirror the core: sort_order in a PATCH is a 0-based REORDER index — move + resequence
      if (typeof patch.sort_order === "number") {
        const ordered = [...SCENES].sort((a, b) => a.sort_order - b.sort_order);
        const from = ordered.indexOf(s);
        ordered.splice(from, 1);
        ordered.splice(Math.max(0, Math.min(ordered.length, patch.sort_order)), 0, s);
        ordered.forEach((sc, i) => { sc.sort_order = i; }); // 0-based, mirroring the core
        const { sort_order, ...rest } = patch;
        Object.assign(s, rest);
        SCENES.sort((a, b) => a.sort_order - b.sort_order); // listScenes returns ordered, like the core
        return { ...s };
      }
      Object.assign(s, patch);
      return { ...s };
    },
    async createScene(_p: number, body: Record<string, unknown>) { await delay(140); const id = SCENES.reduce((mx, s) => Math.max(mx, s.id), 0) + 1; const s = scene({ id, title: String((body.title as string) ?? "New Scene"), content: "", sort_order: SCENES.length + 1, order_index: SCENES.length + 1 }); SCENES.push(s); return { ...s }; },
    async deleteScene(_p: number, sceneId: number) { await delay(120); const i = SCENES.findIndex((x) => x.id === sceneId); if (i >= 0) SCENES.splice(i, 1); },
    async listLogosActions(_p: number, section?: string) {
      await delay(120);
      const defs: [string, string, string][] = [
        ["inline_rewrite", "Rewrite", "generative"], ["inline_expand", "Expand", "generative"],
        ["inline_compress", "Compress", "generative"], ["inline_improve_dialogue", "Improve Dialogue", "generative"],
        ["inline_improve_action", "Improve Action", "generative"], ["inline_make_visual", "Make More Visual", "generative"],
        ["inline_summarize", "Summarize", "diagnostic"], ["inline_suggest", "Suggest", "diagnostic"],
        ["inline_explain", "Explain", "diagnostic"], ["connect_to_psyke", "Connect to PSYKE", "diagnostic"],
      ];
      const noSel = new Set(["inline_suggest", "inline_explain", "connect_to_psyke"]);
      return defs.map(([name, label, category]) => ({
        name, label, description: `${label} the selection`, category, sections: [section || "Inline"],
        needs_selection: !noSel.has(name), deterministic: name === "connect_to_psyke",
        generative: category === "generative",
      }));
    },
    async runLogos(_p: number, body: Record<string, unknown>) {
      await delay(280);
      const action = String(body.action ?? "");
      const sel = String(body.selected_text ?? "").trim();
      if (action === "connect_to_psyke") {
        return { ok: true, action, title: "Connect to PSYKE", message: sel ? "Related PSYKE entries:\n- Marlow (character)\n- Vesper (character)" : "Select some text first.", suggestions: ["Marlow", "Vesper"], proposed_operations: [], generative: false, error: null };
      }
      const generative = /rewrite|expand|compress|improve|make_visual/.test(action);
      const message = generative ? (sel ? `${sel} — [mock ${action}]` : "Select text to transform.") : `[mock] ${action} — a short ${action.includes("summar") ? "summary" : "note"} for the passage.`;
      return { ok: true, action, title: action, message, suggestions: generative ? [] : ["A mock suggestion."], proposed_operations: [], generative, error: null };
    },
    async listLogosProactive(_p: number, section?: string) {
      await delay(180);
      const all = [
        { id: "s1", type: "character", title: "VESPER thinning out", message: "Vesper hasn't appeared in 4 scenes — re-thread her?", section_name: "Manuscript", evidence: "absent in SC.10–13", confidence: 0.78, severity: "warning", target_type: "psyke_entry", target_id: "2", suggested_actions: ["connect_to_psyke"] },
        { id: "s2", type: "pacing", title: "Echoing scenes", message: "SC.14 echoes SC.10 — tighten or cut?", section_name: "Manuscript", evidence: "similar beats", confidence: 0.66, severity: "info", target_type: "scene", target_id: "14", suggested_actions: ["inline_compress"] },
        { id: "s3", type: "psyke", title: "Unlinked cast", message: "MARLOW has no PSYKE bible entry.", section_name: "PSYKE", evidence: "1 of 5 unlinked", confidence: 0.71, severity: "info", target_type: "psyke_entry", target_id: "1", suggested_actions: [] },
      ];
      return section ? all.filter((s) => s.section_name === section) : all;
    },
    async listContinuity(_p: number, sceneId: number) { await delay(120); return (MOCK_CONTINUITY[sceneId] ?? []).map((m) => ({ ...m })); },
    async addContinuity(_p: number, sceneId: number, body: Record<string, unknown>) { await delay(140); const row = { id: 1000 + (MOCK_CONTINUITY[sceneId]?.length ?? 0), scene_id: sceneId, target: "", kind: "state", value: "", ...body }; (MOCK_CONTINUITY[sceneId] ??= []).push(row); return { ...row }; },
    async listGnContinuityItems() { await delay(120); return MOCK_GN_ITEMS.map((i) => ({ ...i })); },
    async createGnContinuityItem(_p: number, body: Record<string, unknown>) { await delay(140); const row = { id: 2000 + MOCK_GN_ITEMS.length, name: "", item_type: "prop", ...body }; MOCK_GN_ITEMS.push(row); return { ...row }; },
    async listGnContinuityAppearances(_p: number, itemId: number) { await delay(120); return MOCK_GN_APPEAR.filter((a) => a.continuity_item_id === itemId).map((a) => ({ ...a })); },
    async createGnContinuityAppearance(_p: number, itemId: number, body: Record<string, unknown>) { await delay(140); const row = { id: 3000 + MOCK_GN_APPEAR.length, continuity_item_id: itemId, ...body }; MOCK_GN_APPEAR.push(row); return { ...row }; },
    async getOutline() { await delay(); return OUTLINE; },
    async listPsyke() { await delay(); return PSYKE.map((e) => ({ ...e })); },
    async listRelations() { await delay(); return RELATIONS.map((r) => ({ ...r })); },
    async listProgressions() { await delay(); return PROGRESSIONS.map((p) => ({ ...p })); },
    async getTimeline() { await delay(); return TIMELINE.map((e) => ({ ...e })); },
    async getPlot() { await delay(); return PLOT.map((b) => ({ ...b })); },
    async getDashboard() {
      await delay();
      const n = SCENES.length;
      return {
        tension: {
          points: SCENES.map((s, i) => ({ scene_id: s.id, scene_order: s.sort_order, scene_title: s.title, score: 30 + (i % 4) * 18, char_count: 1 + (i % 3), relation_pairs: i % 2, keyword_hits: i % 3, progression_count: i === n - 1 ? 1 : 0 })),
          flags: ["Flat section: scenes 3–5", "Weak buildup in first third"],
        },
        characters: PSYKE.filter((e) => e.type === "character").map((e) => ({ entry_id: e.id, name: e.name, present_scenes: [1, 5], total_scenes: n, flags: e.name === "THE WARDEN" ? ["Absent for 4 consecutive scenes"] : [] })),
        structure: { segments: [{ label: "ACT I", scene_count: 3, word_count: 140 }, { label: "ACT II", scene_count: 3, word_count: 260 }, { label: "ACT III", scene_count: 1, word_count: 60 }], total_scenes: n, total_words: 460, flags: [], inferred: false },
        themes: PSYKE.filter((e) => e.type === "theme").map((e, i) => ({ entry_id: e.id, name: e.name, present_scenes: [2], total_scenes: n, flags: ["Underused"], presence_source: i === 0 ? "controlling_idea" : "prose" })),
      };
    },
    async getContinuity() {
      await delay();
      return {
        writing_mode: "screenplay",
        issues: [
          { id: "c2", issue_type: "state_drift", dimension: "character", severity: "blocking", confidence: "confirmed", title: "Vesper's stance contradicts an earlier scene", explanation: "She withholds in Observation Ring but already confessed earlier.", suggested_action: "Reconcile the confession order.", related_scene_ids: [2, 12], status: "open" },
          { id: "c1", issue_type: "location_jump", dimension: "spatial", severity: "warning", confidence: "likely", title: "Location jump without transition", explanation: "Scene moves to the reactor with no bridging beat.", suggested_action: "Add a transition or establish the move.", related_scene_ids: [12, 21], status: "open" },
        ],
        blocking_count: 1,
        warning_count: 1,
        unavailable: [],
      };
    },
    async getPacing() {
      await delay();
      return [
        { text: "THE WARDEN disappears for 4 scenes in a row (~40% of the story).", severity: 0.6, category: "disappearance" },
        { text: "4 consecutive scenes use the same character set (reads as repetitive).", severity: 0.5, category: "monotony" },
      ];
    },
    async getBalance() {
      await delay();
      const chars = PSYKE.filter((e) => e.type === "character");
      return {
        characters: chars.map((c, i) => ({ char_id: c.id, name: c.name, scene_count: [5, 3, 1][i] ?? 1, total_scenes: 7, flag: i === 0 ? "dominant" : i === 2 ? "underused" : "" })),
        arcs: [{ plotline: "MAIN · Marlow", scene_count: 3, acts_spanned: 3, flag: "" }, { plotline: "THREAT · Warden", scene_count: 1, acts_spanned: 1, flag: "thin" }],
        total_scenes: 7,
      };
    },
    async getStoryHealth() {
      await delay();
      return {
        structure: { label: "Partial", level: "sparse", score: 0.55 },
        characters: { label: "Balanced", level: "balanced", score: 0.72 },
        arcs: { label: "Partial", level: "sparse", score: 0.5 },
        density: { label: "Developed", level: "balanced", score: 0.66 },
      };
    },
    async getStructureAnalysis() {
      await delay();
      return {
        issues: [
          { issue_type: "weak_middle", category: "act_balance", severity: 0.6, message: "Middle section (Act II) is thin compared to outer acts.", suggestion: "Add subplots, reversals, or deeper conflict to the middle." },
          { issue_type: "flat_pacing", category: "tension_curve", severity: 0.5, message: "Tension is flat — scenes have similar intensity throughout.", suggestion: "Alternate high-tension and reflective scenes." },
          { issue_type: "missing_beats", category: "beat_placement", severity: 0.35, message: "Missing beats: All Is Lost, Finale.", suggestion: "Add a scene for All Is Lost to strengthen structure." },
        ],
        suggestions: ["Add subplots, reversals, or deeper conflict to the middle.", "Alternate high-tension and reflective scenes."],
      };
    },
    async getWorkflows() {
      await delay();
      return [
        {
          id: 1, title: "Rewrite Pass", status: "active", writing_mode: "screenplay", template_id: "rewrite_pass", current_step_id: "s2", total_steps: 4, completed_steps: 1,
          steps: [
            { step_id: "s1", title: "Run continuity check", status: "completed", sort_index: 0, section_name: "Review", action_id: "continuity" },
            { step_id: "s2", title: "Confirm beat plan", status: "active", sort_index: 1, section_name: "Plan", action_id: "" },
            { step_id: "s3", title: "Apply rewrites", status: "pending", sort_index: 2, section_name: "Apply", action_id: "" },
            { step_id: "s4", title: "Final read", status: "pending", sort_index: 3, section_name: "Review", action_id: "" },
          ],
        },
      ];
    },
    async getDecisionRadar(p: number) {
      await delay();
      return {
        project_id: p,
        generated_light: false,
        summary_line: "Decision radar: 1 blocking, 2 warning, 1 suggestion.",
        radar: [
          { id: "d1", category: "continuity", severity: "blocking", confidence: "confirmed", title: "Vesper's stance contradicts an earlier scene", explanation: "She withholds in Observation Ring but confessed earlier.", suggested_action: "Reconcile the confession order.", related_section: "Continuity", related_target_type: "scene", related_target_id: 12, created_from: "deterministic" },
          { id: "d2", category: "structure", severity: "warning", confidence: "likely", title: "Middle act is underdeveloped", explanation: "Act II is thin compared to the outer acts.", suggested_action: "Add complications or a subplot.", related_section: "Structure", related_target_type: "", related_target_id: null, created_from: "deterministic" },
          { id: "d3", category: "psyke", severity: "warning", confidence: "possible", title: "THE WARDEN has no progression", explanation: "Static arc — no scene-pinned states.", suggested_action: "Add progression milestones.", related_section: "PSYKE", related_target_type: "psyke", related_target_id: 3, created_from: "deterministic" },
          { id: "d4", category: "export", severity: "suggestion", confidence: "likely", title: "2 scenes missing slug lines", explanation: "Fountain export flagged missing slugs.", suggested_action: "Add scene headings.", related_section: "Export", related_target_type: "", related_target_id: null, created_from: "deterministic" },
        ],
      };
    },
    async generateQuantumOutline(_p: number, body: { premise?: string }) {
      await delay(500);
      return {
        kind: "wavefunction",
        title: "Quantum outline · " + (body.premise || "untitled").slice(0, 40),
        body: "Generated 4 opening branches in superposition.",
        payload: {
          wavefunction_id: "wf_mock_1", anchor: body.premise || "",
          recommendation: { branch_id: "b2", title: "Deviation", probability: 0.42, reason: "Highest tension gain with consistent PSYKE state." },
          branches: [
            { id: "b1", title: "Intensification", description: "Marlow forces the confrontation now.", stakes: "high", consequence: "Vesper retreats further.", score: 7.4, probability: 0.31, branch_type: "escalate", is_pareto_optimal: true, factors: {} },
            { id: "b2", title: "Deviation", description: "A new signal pulls focus to the black box.", stakes: "medium", consequence: "The Warden's count pauses.", score: 8.1, probability: 0.42, branch_type: "swerve", is_pareto_optimal: true, factors: {} },
            { id: "b3", title: "Resolution", description: "Vesper finally confesses.", stakes: "high", consequence: "Static goes quiet.", score: 6.8, probability: 0.27, branch_type: "resolve", is_pareto_optimal: false, factors: {} },
          ],
        },
      };
    },
    async generateQuantumBranches(_p: number, body: { situation?: string }) {
      await delay(500);
      return {
        kind: "wavefunction",
        title: "Next moves · " + (body.situation || "").slice(0, 40),
        body: "Generated next-move branches.",
        payload: {
          wavefunction_id: "wf_mock_2", anchor: body.situation || "",
          branches: [
            { id: "n1", title: "Press", description: "Push the interrogation.", score: 7.0, probability: 0.5, factors: {} },
            { id: "n2", title: "Withdraw", description: "Let the silence work.", score: 6.5, probability: 0.5, factors: {} },
          ],
        },
      };
    },
    async getGraphGravity() {
      await delay();
      const chars = PSYKE.filter((e) => e.type === "character");
      const nodes = [
        ...chars.map((c, i) => ({ node_id: `PSYKE:${c.id}`, etype: "PSYKE", name: c.name, narrative: Math.max(0, 0.85 - i * 0.18), thematic: 0.2, structural: Math.max(0, 0.45 - i * 0.1), total: Math.max(0.1, 0.62 - i * 0.14) })),
        { node_id: "Scene:12", etype: "Scene", name: "Observation Ring", narrative: 0.7, thematic: 0.5, structural: 0.8, total: 0.66 },
        { node_id: "Act:1", etype: "Act", name: "ACT II", narrative: 0.1, thematic: 0.0, structural: 0.6, total: 0.17 },
      ].sort((a, b) => b.total - a.total);
      return { weights: { narrative: 0.45, thematic: 0.35, structural: 0.2 }, glow_threshold: 0.55, available: true, nodes };
    },
    async runCounterpart(_p: number, body: { mode?: string }) {
      await delay(500);
      return {
        reply: `[COUNTERPART · ${body.mode || "Feedback"}]\n\nThe scene leans on the static as a mood device, but the Warden's count is stated, not felt — it never lands as a threat. Vesper's competence reads as a wall, which is good; the reader just needs one crack in it. What does she lose if she finally names the Warden?`,
        cached: false,
      };
    },
    async listExtractionModels() {
      await delay(120);
      return { models: ["llama-3.2-8x3b-moe-dark-champion-18.4b", "davidau.l3.2-8x4b-moe-v2-dark-champion-21b", "qwen/qwen2.5-coder-32b", "qwen/qwen3.6-27b"], active: "llama-3.2-8x3b-moe-dark-champion-18.4b" };
    },
    async startExtract(p: number, useLlm = true) {
      await delay(300);
      const sc = SCENES.slice(0, 4);
      const result = {
        project_id: p,
        used_llm: useLlm,
        scenes: sc.map((s, i) => ({
          scene_id: s.id,
          title: s.title,
          characters: i % 2 === 0 ? ["VESPER", "MARLOW"] : ["MARLOW", "THE WARDEN"],
          who_knows_what: useLlm
            ? i === 0 ? "Vesper knows the relay order was hers; Marlow does not."
              : i === 1 ? "Marlow suspects the Warden is counting heartbeats." : ""
            : "",
          relations: useLlm && i === 0
            ? [
                { source: "Vesper", target: "Marlow", rel_type: "subtext_opposition", why: "she deflects to keep her confession at arm's length", confidence: 0.72, source_status: "existing", target_status: "existing" },
                // a typo'd name carries an advisory near-dup hint (display-only)
                { source: "Marlowe", target: "Vesper", rel_type: "visual_motif", why: "the misspelled cue would mint a stray entry", confidence: 0.6, source_status: "new", source_hint: { existing_id: 1, existing_name: "MARLOW", score: 0.91 }, target_status: "existing" },
              ]
            : [],
        })),
        setup_payoffs: useLlm
          ? [{ source: "the relay order", target: "the Kessler crew's fate", rel_type: "supports_setup", why: "planted as Vesper's secret, pays off as her wound", confidence: 0.6 }]
          : [],
      };
      const jobId = `mockjob${++MOCK_EXTRACT_SEQ}`;
      MOCK_EXTRACT_JOBS[jobId] = { done: 0, total: 6, result };
      return { job_id: jobId, status: "running", done: 0, total: 6 };
    },
    async getExtractJob(_p: number, jobId: string) {
      await delay(350);
      const j = MOCK_EXTRACT_JOBS[jobId];
      if (!j) return { job_id: jobId, status: "error", done: 0, total: 0, error: "unknown job" };
      j.done = Math.min(j.total, j.done + 2);
      return j.done < j.total
        ? { job_id: jobId, status: "running", done: j.done, total: j.total }
        : { job_id: jobId, status: "done", done: j.total, total: j.total, result: j.result };
    },
    async applyExtraction(_p: number, body: { scenes?: { scene_id?: number; characters?: string[]; who_knows_what?: string; relations?: unknown[] }[]; setup_payoffs?: unknown[] }) {
      await delay(500);
      const scenes = body?.scenes ?? [];
      const sp = body?.setup_payoffs ?? [];
      const names = new Set<string>();
      scenes.forEach((s) => (s.characters ?? []).forEach((c) => names.add(c.toLowerCase())));
      const links = scenes.reduce((n, s) => n + (s.characters?.length ?? 0), 0);
      const wkw = scenes.filter((s) => (s.who_knows_what ?? "").trim()).length;
      const rels = scenes.reduce((n, s) => n + (s.relations?.length ?? 0), 0) + sp.length;
      const receipt = {
        character_ids: Array.from(names, (_, i) => 900 + i),
        links: scenes.flatMap((s) => (s.characters ?? []).map((_, j) => [s.scene_id ?? 0, 900 + j])),
        wkw_scene_ids: scenes.filter((s) => (s.who_knows_what ?? "").trim()).map((s) => s.scene_id ?? 0),
        psyke_ids: [] as number[],
        relations: [] as unknown[],
      };
      return { characters_created: names.size, links_added: links, who_knows_what_set: wkw, psyke_created: rels, relations_added: rels, receipt };
    },
    async revertExtraction(_p: number, receipt: { character_ids?: number[]; links?: number[][]; wkw_scene_ids?: number[]; psyke_ids?: number[]; relations?: unknown[] }) {
      await delay(400);
      return {
        characters_created: (receipt.character_ids ?? []).length,
        links_added: (receipt.links ?? []).length,
        who_knows_what_set: (receipt.wkw_scene_ids ?? []).length,
        psyke_created: (receipt.psyke_ids ?? []).length,
        relations_added: (receipt.relations ?? []).length,
      };
    },
    // --- format-specific structured data (authoring) ---
    async listGnPages() { await delay(); return MOCK_GN_PAGES.slice(); },
    async syncGnFromScenes() { await delay(300); return { pages: MOCK_GN_PAGES.length, panels: 0, skipped: MOCK_GN_PAGES.length > 0 }; },
    async createGnPage(_p: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, page_number: (b.page_number as number) || MOCK_GN_PAGES.length + 1, summary: (b.summary as string) || "", reveal_type: (b.reveal_type as string) || "", splash_page: !!b.splash_page }; MOCK_GN_PAGES.push(row); return row; },
    async listGnPanels(_p: number, pageId: number) { await delay(); return MOCK_GN_PANELS.filter((x) => x.page_id === pageId); },
    async createGnPanel(_p: number, pageId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, page_id: pageId, panel_number: (b.panel_number as number) || 0, description: (b.description as string) || "", visual_motifs: (b.visual_motifs as string[]) || [] }; MOCK_GN_PANELS.push(row); return row; },
    async listStageCues(_p: number, sceneId: number) { await delay(); return MOCK_STAGE_CUES.filter((x) => x.scene_id === sceneId); },
    async createStageCue(_p: number, sceneId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, scene_id: sceneId, cue_type: (b.cue_type as string) || "other", cue_text: (b.cue_text as string) || "" }; MOCK_STAGE_CUES.push(row); return row; },
    async listStageEntrances(_p: number, sceneId: number) { await delay(); return MOCK_STAGE_ENTR.filter((x) => x.scene_id === sceneId); },
    async createStageEntrance(_p: number, sceneId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, scene_id: sceneId, type: (b.type as string) || "entrance", character_id: (b.character_id as number) ?? null, cue_text: (b.cue_text as string) || "" }; MOCK_STAGE_ENTR.push(row); return row; },
    async syncStageFromScenes() { await delay(300); return { cues: MOCK_STAGE_CUES.length, entrances: MOCK_STAGE_ENTR.length, offstage: 0 }; },
    async listStageBusiness(_p: number, sceneId: number) { await delay(); return MOCK_STAGE_BIZ.filter((x) => x.scene_id === sceneId); },
    async createStageBusiness(_p: number, sceneId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, scene_id: sceneId, prop_psyke_entry_id: (b.prop_psyke_entry_id as number) ?? null, character_id: (b.character_id as number) ?? null, stage_action: (b.stage_action as string) || "" }; MOCK_STAGE_BIZ.push(row); return row; },
    async listSeasons() { await delay(); return MOCK_SEASONS.slice(); },
    async createSeason(_p: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, season_number: (b.season_number as number) || MOCK_SEASONS.length + 1, title: (b.title as string) || "" }; MOCK_SEASONS.push(row); return row; },
    async listEpisodes() { await delay(); return MOCK_EPISODES.slice(); },
    async createEpisode(_p: number, seasonId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, season_id: seasonId, episode_number: (b.episode_number as number) || MOCK_EPISODES.length + 1, title: (b.title as string) || "", logline: (b.logline as string) || "" }; MOCK_EPISODES.push(row); return row; },
    async listSeriesArcs() { await delay(); return MOCK_ARCS.slice(); },
    async createSeriesArc(_p: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, scope: (b.scope as string) || "series", title: (b.title as string) || "", setup_episode_id: (b.setup_episode_id as number) ?? null, payoff_episode_id: (b.payoff_episode_id as number) ?? null, status: (b.status as string) || "active" }; MOCK_ARCS.push(row); return row; },
    async listEpisodePlotlines(_p: number, episodeId: number) { await delay(); return MOCK_PLOTLINES.filter((x) => x.episode_id === episodeId); },
    async createEpisodePlotline(_p: number, episodeId: number, b: Record<string, unknown>) { await delay(300); const row = { id: ++MOCK_FD_SEQ, episode_id: episodeId, type: (b.type as string) || "A", title: (b.title as string) || "", resolution_state: "" }; MOCK_PLOTLINES.push(row); return row; },
    async getSeriesMemory(_p: number, entryId: number) { await delay(); return MOCK_SERIES_MEM[entryId] ?? { entry_id: entryId, continuity_flags: "", current_status_by_episode: {} }; },
    async setSeriesMemory(_p: number, entryId: number, b: Record<string, unknown>) { await delay(200); const row = { entry_id: entryId, continuity_flags: (b.continuity_flags as string) || "", current_status_by_episode: (b.current_status_by_episode as Record<string, string>) || {} }; MOCK_SERIES_MEM[entryId] = row; return row; },
    async getSettings() { await delay(); return { settings: { ...SETTINGS } }; },
    async patchSettings(_p: number, body: { settings?: Record<string, unknown> }) { await delay(); SETTINGS = { ...SETTINGS, ...(body?.settings ?? {}) }; return { settings: { ...SETTINGS } }; },
    async export(_p: number, req: ExportRequestDTO): Promise<ExportResponseDTO> {
      await delay();
      if (req.format === "json") {
        const payload = { export_type: req.export_type, project: "Null Horizon", scenes: SCENES.map((s) => ({ id: s.id, title: s.title, act: s.act })), psyke: PSYKE.map((e) => ({ name: e.name, type: e.type })) };
        return { export_type: req.export_type, format: "json", payload, content: null, files: null };
      }
      if (req.format === "csv") {
        const content = "id,title,act\n" + SCENES.map((s) => `${s.id},"${s.title}","${s.act}"`).join("\n");
        return { export_type: req.export_type, format: "csv", content, payload: null, files: null };
      }
      const content =
        `# Null Horizon\n\n_${req.export_type} · markdown_\n\n## Scenes (${SCENES.length})\n` +
        SCENES.map((s) => `- **${s.title}** — ${s.summary}`).join("\n") +
        `\n\n## PSYKE (${PSYKE.length})\n` + PSYKE.map((e) => `- ${e.name} (${e.type})`).join("\n");
      return { export_type: req.export_type, format: "markdown", content, payload: null, files: null };
    },
  } as unknown as ApiClient;
}
