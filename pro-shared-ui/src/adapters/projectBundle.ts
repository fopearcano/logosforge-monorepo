import type {
  ProgressionAnchorKind,
  ProgressionCommandDTO,
  ProgressionKind,
  ProgressionSnapshotDTO,
  WhiteboardImportBlockDTO,
  WhiteboardImportCommentDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "./api";
import { ApiRequestError, ApiRequestTimeoutError } from "./httpApiClient";

/**
 * A LogosForge project bundle (`.lfbundle`) — the single-project migration
 * artifact exported by Whiteboard (File → Export → Export Project). One bundle
 * carries a whole project: manuscript blocks + the PSYKE story bible (entries,
 * relations and progression beats), the manual outline, and inline comments.
 * The format is a fixed contract owned by the Whiteboard exporter — this module
 * only READS it and orchestrates existing Pro endpoints.
 */
export interface ProjectBundlePsykeElement {
  id?: string;
  name?: string;
  entry_type?: string;      // character | place | object | lore | theme | other
  aliases?: string[];
  description?: string;     // free text; Whiteboard round-trips it via details.description
  notes?: string;
}

/** Canonical relation DTO written by the Whiteboard bundle exporter. IDs refer
 * to source-project PSYKE entries and therefore must be remapped on import. */
export interface ProjectBundlePsykeRelation {
  id?: string;
  source_id?: number;
  target_id?: number;
  source?: string;
  target?: string;
  relation_type?: string;
}

/** Canonical progression DTO written by the Whiteboard bundle exporter. Both
 * entry_id and scene_id belong to the source project; neither may be reused in
 * the newly-created Pro project. */
export interface ProjectBundlePsykeProgression {
  id?: number;
  entry_id?: number;
  text?: string;
  scene_id?: number | null;
  scene_title?: string;
  sort_order?: number;
}

/** Additive first-class Progressions payload (bundle v1.0 remains valid).
 * Source ids are provenance only and are always remapped on import. */
export interface ProjectBundleProgressionBeat {
  id?: number;
  track_id?: number;
  text?: string;
  sort_order?: number;
  anchor_kind?: ProgressionAnchorKind;
  scene_id?: number | null;
  scene_title?: string;
  anchor_ref?: string | null;
  anchor_label?: string;
}

export interface ProjectBundleProgressionTrack {
  id?: number;
  kind?: ProgressionKind;
  title?: string;
  description?: string;
  color_label?: string;
  sort_order?: number;
  legacy_compatibility?: boolean;
  primary_psyke_entry_id?: number | null;
  primary_psyke_entry_name?: string;
  primary_psyke_entry_type?: string;
  secondary_psyke_entry_id?: number | null;
  secondary_psyke_entry_name?: string;
  secondary_psyke_entry_type?: string;
  beats?: ProjectBundleProgressionBeat[];
}

/** A Whiteboard manual-outline node. Flat list; the tree is `parentId` + `order`.
 * Richer than Pro's node (which has only title/description/parent/sort_order), so
 * the extra metadata is folded into the imported node's description. */
export interface ProjectBundleOutlineNode {
  id?: string;
  parentId?: string | null;
  type?: string;            // act | part | chapter | sequence | scene | beat | custom
  title?: string;
  summary?: string;         // writer-authored synopsis / intent
  order?: number;
  status?: string;          // none | todo | drafting | done | …
  colorLabel?: string;      // none | blue | green | …
  tags?: string[];
  completed?: boolean;
  // Phase 3 — optional hard link to a manuscript block ("this node owns the
  // manuscript from here"). `blockIndex` is 0-based into project.manuscript.blocks;
  // `quote` is a snapshot used as a sanity check. Newer Whiteboard bundles also
  // carry `blockId`; Pro still resolves through blockIndex because scene
  // segmentation is index-based, but recognizing the additive field keeps the
  // reader contract honest and forward-compatible.
  link?: { blockIndex: number; quote?: string; blockId?: string } | null;
}

/** A project-scoped Whiteboard Drafter page. Drafter text is deliberately
 * non-canonical: it must become a Pro Note, never a manuscript scene. The
 * original blocks are also retained in project settings so marks and
 * screenplay element metadata survive the migration losslessly. */
export interface ProjectBundleDrafterPage {
  id?: string;
  title?: string;
  blocks?: WhiteboardImportBlockDTO[];
  created_at?: string;
  updated_at?: string;
}

export interface ProjectBundle {
  format?: string;
  version?: string;
  project?: {
    id?: string;
    title?: string;
    mode?: string;          // novel | screenplay | scene | graphic_novel | stage_script
    settings?: Record<string, unknown>; // project-scoped Whiteboard voice/format settings
    manuscript?: { blocks?: WhiteboardImportBlockDTO[] };
    psyke?: {
      elements?: ProjectBundlePsykeElement[];
      relations?: ProjectBundlePsykeRelation[];
      progressions?: ProjectBundlePsykeProgression[];
    };
    progression_tracks?: ProjectBundleProgressionTrack[];
    outline?: ProjectBundleOutlineNode[];   // Phase 2 — imported
    comments?: WhiteboardImportCommentDTO[];
    drafter?: { pages?: ProjectBundleDrafterPage[] };
  };
}

export interface BundleImportResult {
  projectId: number;
  title: string;
  mode: string;
  scenes: number;
  settingsImported: boolean;
  settingsSkipped: boolean;
  entries: number;          // PSYKE bible entries created
  entriesSkipped: number;   // invalid, duplicate, or failed PSYKE rows
  relations: number;        // PSYKE relationships recreated with remapped ids
  relationsSkipped: number; // invalid, duplicate, unmappable, or failed rows
  progressions: number;     // PSYKE progression beats recreated
  progressionsSkipped: number; // invalid, unmappable, or failed rows
  progressionSceneLinks: number; // source scene anchors resolved to new scenes
  progressionSceneLinksSkipped: number; // linked beats kept, but unanchored
  progressionTracks: number; // first-class canonical tracks recreated
  progressionTracksSkipped: number;
  progressionTrackBeats: number; // beats recreated inside canonical tracks
  progressionTrackBeatsSkipped: number;
  progressionTrackSceneLinks: number;
  progressionTrackSceneLinksSkipped: number;
  outlineNodes: number;     // outline nodes recreated (Phase 2)
  outlineSkipped: number;   // outline rows whose create call failed
  outlineReparented: number;// missing/cyclic/failed parents that fell back to root
  outlineDuplicateIds: number; // duplicate source ids (all rows still imported)
  comments: number;         // inline comment threads created
  commentsSkipped: number;  // stale or otherwise unmappable comment threads
  commentReplies: number;   // replies created with their parent threads
  commentRepliesSkipped: number; // replies rejected while importing a thread
  drafterPages: number;     // project-scoped scratch pages recreated as Pro Notes
  drafterPagesSkipped: number; // invalid or failed Drafter-page Note creations
  drafterArchivePreserved: boolean; // exact structured blocks retained in settings
  drafterArchiveSkipped: boolean;
  links: number;            // outline→scene hard links reconstructed (Phase 3)
  linksSkipped: number;     // outline nodes that carried a link that couldn't be resolved
}

export const BUNDLE_FORMAT = "logosforge-project-bundle";

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function positiveSafeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0
    ? value
    : null;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

/** Whiteboard serializes PSYKE entry ids as decimal strings. Normalize them to
 * numbers so they can be matched against relation/progression DTO references,
 * while rejecting imprecise values rather than silently rounding an id. */
function sourceEntryId(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) return null;
  const parsed = Number(normalized);
  return positiveSafeInteger(parsed);
}

function entryKey(element: ProjectBundlePsykeElement): string {
  const name = typeof element.name === "string" ? element.name.trim() : "";
  const type = typeof element.entry_type === "string" && element.entry_type
    ? element.entry_type
    : "other";
  return JSON.stringify([type, name]);
}

/**
 * Parse + validate a `.lfbundle`'s text. Throws a user-facing `Error` on bad
 * JSON or a file that isn't a project bundle. Tolerant of a future `version`
 * bump (same top-level shape) and of a missing outline/comments/psyke (older or
 * smaller bundles — treated as empty).
 */
export function parseProjectBundle(text: string): ProjectBundle {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("That file isn't valid JSON.");
  }
  if (!isRecord(parsed) || parsed.format !== BUNDLE_FORMAT) {
    throw new Error("That isn't a LogosForge project bundle (.lfbundle).");
  }
  if (!isRecord(parsed.project)) {
    throw new Error("This bundle has no project data.");
  }
  const project = parsed.project;
  if (!isRecord(project.manuscript) || !Array.isArray(project.manuscript.blocks)) {
    throw new Error("This bundle has no manuscript block list.");
  }
  if (project.manuscript.blocks.some((block) => !isRecord(block))) {
    throw new Error("This bundle contains an invalid manuscript block.");
  }
  if (project.title != null && typeof project.title !== "string") {
    throw new Error("This bundle has an invalid project title.");
  }
  if (project.mode != null && typeof project.mode !== "string") {
    throw new Error("This bundle has an invalid writing mode.");
  }
  if (project.settings != null && !isRecord(project.settings)) {
    throw new Error("This bundle has an invalid document settings section.");
  }
  if (project.psyke != null) {
    if (!isRecord(project.psyke) ||
        (project.psyke.elements != null && !Array.isArray(project.psyke.elements))) {
      throw new Error("This bundle has an invalid PSYKE section.");
    }
    if (Array.isArray(project.psyke.elements) &&
        project.psyke.elements.some((element) => !isRecord(element))) {
      throw new Error("This bundle contains an invalid PSYKE entry.");
    }
    if (project.psyke.relations != null && !Array.isArray(project.psyke.relations)) {
      throw new Error("This bundle has an invalid PSYKE relations section.");
    }
    if (Array.isArray(project.psyke.relations) &&
        project.psyke.relations.some((relation) => !isRecord(relation))) {
      throw new Error("This bundle contains an invalid PSYKE relation.");
    }
    if (project.psyke.progressions != null && !Array.isArray(project.psyke.progressions)) {
      throw new Error("This bundle has an invalid PSYKE progressions section.");
    }
    if (Array.isArray(project.psyke.progressions) &&
        project.psyke.progressions.some((progression) => !isRecord(progression))) {
      throw new Error("This bundle contains an invalid PSYKE progression.");
    }
  }
  if (project.progression_tracks != null && !Array.isArray(project.progression_tracks)) {
    throw new Error("This bundle has an invalid Progressions tracks section.");
  }
  if (Array.isArray(project.progression_tracks)) {
    const kinds = new Set(["story", "character", "relationship", "theme", "world", "custom"]);
    const anchors = new Set(["unanchored", "scene", "document_block"]);
    for (const track of project.progression_tracks) {
      if (!isRecord(track) || !Array.isArray(track.beats)) {
        throw new Error("This bundle contains an invalid Progressions track.");
      }
      if (typeof track.title !== "string" || typeof track.kind !== "string" || !kinds.has(track.kind)) {
        throw new Error("This bundle contains an invalid Progressions track.");
      }
      if (track.legacy_compatibility != null && typeof track.legacy_compatibility !== "boolean") {
        throw new Error("This bundle contains an invalid Progressions compatibility marker.");
      }
      if (track.primary_psyke_entry_id != null && positiveSafeInteger(track.primary_psyke_entry_id) == null) {
        throw new Error("This bundle contains an invalid Progressions PSYKE reference.");
      }
      if (track.secondary_psyke_entry_id != null && positiveSafeInteger(track.secondary_psyke_entry_id) == null) {
        throw new Error("This bundle contains an invalid Progressions PSYKE reference.");
      }
      for (const beat of track.beats) {
        if (!isRecord(beat) || typeof beat.text !== "string" ||
            typeof beat.anchor_kind !== "string" || !anchors.has(beat.anchor_kind)) {
          throw new Error("This bundle contains an invalid Progressions beat.");
        }
        if (beat.scene_id != null && positiveSafeInteger(beat.scene_id) == null) {
          throw new Error("This bundle contains an invalid Progressions scene reference.");
        }
        if (beat.anchor_ref != null && typeof beat.anchor_ref !== "string") {
          throw new Error("This bundle contains an invalid Progressions document reference.");
        }
      }
    }
  }
  if (project.outline != null && !Array.isArray(project.outline)) {
    throw new Error("This bundle has an invalid outline section.");
  }
  if (Array.isArray(project.outline) && project.outline.some((node) => !isRecord(node))) {
    throw new Error("This bundle contains an invalid outline node.");
  }
  if (project.comments != null && !Array.isArray(project.comments)) {
    throw new Error("This bundle has an invalid comments section.");
  }
  if (Array.isArray(project.comments)) {
    for (const comment of project.comments) {
      if (!isRecord(comment)) {
        throw new Error("This bundle contains an invalid inline comment.");
      }
      if (!isRecord(comment.anchor)) {
        throw new Error("This bundle contains an invalid inline comment anchor.");
      }
      if (comment.replies != null && !Array.isArray(comment.replies)) {
        throw new Error("This bundle contains an invalid inline comment replies section.");
      }
      if (Array.isArray(comment.replies) && comment.replies.some((reply) => !isRecord(reply))) {
        throw new Error("This bundle contains an invalid inline comment reply.");
      }
    }
  }
  if (project.drafter != null) {
    if (!isRecord(project.drafter) ||
        (project.drafter.pages != null && !Array.isArray(project.drafter.pages))) {
      throw new Error("This bundle has an invalid Drafter section.");
    }
    if (Array.isArray(project.drafter.pages)) {
      for (const page of project.drafter.pages) {
        if (!isRecord(page)) {
          throw new Error("This bundle contains an invalid Drafter page.");
        }
        if (page.id != null && typeof page.id !== "string") {
          throw new Error("This bundle contains an invalid Drafter page id.");
        }
        if (page.title != null && typeof page.title !== "string") {
          throw new Error("This bundle contains an invalid Drafter page title.");
        }
        if (!Array.isArray(page.blocks) || page.blocks.some((block) => !isRecord(block))) {
          throw new Error("This bundle contains an invalid Drafter page block list.");
        }
        if ((page.created_at != null && typeof page.created_at !== "string") ||
            (page.updated_at != null && typeof page.updated_at !== "string")) {
          throw new Error("This bundle contains an invalid Drafter page timestamp.");
        }
      }
    }
  }
  return parsed as ProjectBundle;
}

/** Produce a readable Note while the settings archive below retains the exact
 * source block DTOs. This intentionally does not segment scratch text into
 * scenes or make it canonical manuscript content. */
function drafterNoteContent(page: ProjectBundleDrafterPage): string {
  const blocks = Array.isArray(page.blocks) ? page.blocks : [];
  return blocks.map((block) => {
    const text = typeof block.text === "string" ? block.text : "";
    if (block.type === "heading") {
      const rawLevel = typeof block.level === "number" && Number.isFinite(block.level)
        ? Math.trunc(block.level)
        : 1;
      const level = Math.max(1, Math.min(6, rawLevel));
      return `${"#".repeat(level)} ${text}`.trimEnd();
    }
    return text;
  }).join("\n\n");
}

/** A short human line preserving the Whiteboard outline metadata Pro's simpler
 * node has no field for (type / status / colour / tags / completed), so it stays
 * visible in the node's description instead of being silently dropped —
 * e.g. `"Act · drafting · blue · #climax"`. Only set parts are included; the
 * Whiteboard "none" sentinel for status/colour is treated as unset. */
function foldOutlineMeta(wb: ProjectBundleOutlineNode): string {
  const parts: string[] = [];
  if (wb.type) parts.push(wb.type.charAt(0).toUpperCase() + wb.type.slice(1));
  if (wb.status && wb.status !== "none") parts.push(wb.status);
  if (wb.completed && wb.status !== "done") parts.push("completed");   // avoid redundant "done · completed"
  if (wb.colorLabel && wb.colorLabel !== "none") parts.push(wb.colorLabel);
  if (Array.isArray(wb.tags)) for (const t of wb.tags) if (t) parts.push(`#${t}`);
  return parts.join(" · ");
}

/** Preserve the writer's actual summary first, then clearly label metadata that
 * Pro does not yet model as structured fields. */
function outlineDescription(wb: ProjectBundleOutlineNode): string {
  const summary = typeof wb.summary === "string" ? wb.summary.trim() : "";
  const meta = foldOutlineMeta(wb);
  if (summary && meta) return `${summary}\n\n[Whiteboard: ${meta}]`;
  return summary || meta;
}

/** Order the flat outline so every node comes after its parent — parents are
 * created first, so their new numeric ids exist when a child references them.
 * Cycles and missing parents are tolerated (the guard breaks a cycle; the node
 * still lands, at root, via the caller's `?? null`). EVERY input node is emitted
 * exactly once — including id-less leaves and nodes with a (corrupt) duplicate
 * id — so nothing is silently dropped. */
function topoSortOutline(nodes: ProjectBundleOutlineNode[]): ProjectBundleOutlineNode[] {
  const valid = nodes.filter((n): n is ProjectBundleOutlineNode => !!n);
  const byId = new Map<string, ProjectBundleOutlineNode>();
  for (const n of valid) if (n.id != null) byId.set(String(n.id), n);
  const sorted: ProjectBundleOutlineNode[] = [];
  // Track visited by node IDENTITY (not id) so two nodes sharing a duplicate id
  // are each placed rather than collapsing to one.
  const done = new Set<ProjectBundleOutlineNode>();
  const onStack = new Set<ProjectBundleOutlineNode>();
  const visit = (n: ProjectBundleOutlineNode) => {
    if (done.has(n) || onStack.has(n)) return;   // already placed, or a cycle → break it
    onStack.add(n);
    const pid = n.parentId != null ? String(n.parentId) : null;
    const parent = pid != null ? byId.get(pid) : undefined;
    if (parent && parent !== n) visit(parent);
    onStack.delete(n);
    done.add(n);
    sorted.push(n);
  };
  for (const n of valid) visit(n);   // drive over EVERY node → none dropped
  return sorted;
}

/** Strip markdown emphasis/heading markers + collapse whitespace + lowercase, so a
 * Whiteboard block's raw `quote` matches the scene text it landed in (the block
 * may have gained `**bold**` markers, or a heading became the scene title). */
function normalizeForQuote(s: string): string {
  return s.replace(/[*#`_~]/g, "").replace(/\s+/g, " ").trim().toLowerCase();
}

/** Resolve an outline node's block-anchored `link` to a Pro scene id, or null.
 * `sceneIdsByBlock[blockIndex]` (from the Phase-1 import) is the authoritative
 * map; `quote` is only a sanity check — if the mapped scene's text doesn't contain
 * the (normalized) quote, the bundle likely predates an edit, so treat it as
 * unresolved. When scene texts aren't available, resolve by index alone. */
function resolveSceneLink(
  link: { blockIndex: number; quote?: string },
  sceneIdsByBlock: number[],
  sceneTextById: Map<number, string>,
): number | null {
  const bi = link.blockIndex;
  if (!Number.isInteger(bi) || bi < 0 || bi >= sceneIdsByBlock.length) return null;
  const sid = sceneIdsByBlock[bi];
  if (sid == null || sid < 0) return null;   // block mapped to no scene
  const quote = normalizeForQuote(String(link.quote ?? ""));
  if (quote && sceneTextById.size) {
    const txt = sceneTextById.get(sid);
    if (txt != null) {
      const probe = quote.length > 60 ? quote.slice(0, 60) : quote;
      if (!normalizeForQuote(txt).includes(probe)) return null;  // quote absent → stale/wrong
    }
  }
  return sid;
}

async function executeBundleProgressionCommand(
  api: ApiClient,
  projectId: number,
  command: ProgressionCommandDTO,
  idempotencyKey: string,
): Promise<ProgressionSnapshotDTO> {
  try {
    const result = await api.executeProgressionCommand(projectId, command, idempotencyKey);
    return result.progressions;
  } catch (firstFailure) {
    if (!isAmbiguousBundleProgressionFailure(firstFailure)) throw firstFailure;
    // An interrupted import may have committed even though the renderer missed
    // the response. Resolve the durable receipt before resending the exact same
    // command/key; the Core prevents a duplicate track or beat either way.
    try {
      await api.getProgressionCommandReceipt(projectId, idempotencyKey, command);
      api.invalidatePendingReads?.();
      return await api.getProgressions(projectId);
    } catch (receiptFailure) {
      if (!isBundleProgressionReceiptMiss(receiptFailure)) {
        throw new BundleProgressionDeliveryUncertainError(
          `The Progressions receipt lookup was inconclusive after an interrupted bundle command: ${failureMessage(receiptFailure)}`,
        );
      }
    }
    try {
      return (await api.executeProgressionCommand(projectId, command, idempotencyKey)).progressions;
    } catch (retryFailure) {
      if (!isAmbiguousBundleProgressionFailure(retryFailure)) throw retryFailure;
      // The sole same-key resend was interrupted too. Reconcile exactly once;
      // a missing/inconclusive receipt is an import barrier, never permission
      // to continue dependent commands from a potentially stale revision.
      try {
        await api.getProgressionCommandReceipt(projectId, idempotencyKey, command);
        api.invalidatePendingReads?.();
        return await api.getProgressions(projectId);
      } catch (receiptFailure) {
        const detail = isBundleProgressionReceiptMiss(receiptFailure)
          ? "No durable receipt is available after the one allowed same-key resend."
          : `The final receipt lookup was inconclusive: ${failureMessage(receiptFailure)}`;
        throw new BundleProgressionDeliveryUncertainError(
          `${detail} Bundle import stopped before any dependent Progressions command could run.`,
        );
      }
    }
  }
}

class BundleProgressionDeliveryUncertainError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BundleProgressionDeliveryUncertainError";
  }
}

function failureMessage(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure);
}

function isAmbiguousBundleProgressionFailure(failure: unknown): boolean {
  if (failure instanceof ApiRequestTimeoutError) return failure.outcomeUnknown;
  if (failure instanceof ApiRequestError) {
    return failure.status === 408 || failure.status === 429 || failure.status >= 500;
  }
  return true;
}

function isBundleProgressionReceiptMiss(failure: unknown): boolean {
  return failure instanceof ApiRequestError
    && failure.code === "progression_receipt_not_found";
}

function rethrowUncertainBundleProgression(failure: unknown): void {
  if (failure instanceof BundleProgressionDeliveryUncertainError) throw failure;
}

/**
 * Import a `.lfbundle` into ONE new Pro project — client-side orchestration over
 * existing endpoints, no core change:
 *   1. Manuscript → reuse the blocks→scenes converter via `api.importWhiteboard`,
 *      which creates the new project (mode-correct) and returns its id.
 *   2. PSYKE → recreate bible entries and retain an old-entry-id → new-entry-id
 *      map. Relations and progression beats are then recreated through their
 *      existing endpoints using only destination ids. Source scene ids are never
 *      reused; a linked progression is re-anchored only when its exact trimmed
 *      scene title identifies one destination scene, otherwise its text is kept
 *      as an unanchored progression.
 *   3. OUTLINE (Phase 2) → recreate the manual outline via `api.createOutlineNode`,
 *      topologically (parents first), remapping the string parentId → the new
 *      numeric parent_id and folding Whiteboard's type/status/colour/tags into
 *      the description. The project is freshly created so its outline is empty →
 *      we append; each create fires `outline_changed` so the panel refreshes.
 *      SECTION↔SCENE LINK (Phase 3) → if a node carries `link.blockIndex`, resolve
 *      it to a scene id via the import's `scene_ids_by_block` map (quote-validated)
 *      and set the node's `scene_id`, so the "this section lives here" association
 *      survives. Unresolvable links are skipped and counted.
 *   4. COMMENTS → pass the source threads with the manuscript blocks in step 1.
 *      The core owns the exact block-local → scene title/content anchor mapping,
 *      so it can account for segmentation, trimming, heading promotion, markup,
 *      and UTF-16 offsets in one deterministic conversion. It reports created and
 *      skipped roots/replies independently.
 *
 * A single failing bible/relationship/progression/outline row is skipped, not
 * fatal. A failure in step 1 propagates (no project should exist without its
 * manuscript); the caller reports it and nothing partial is opened.
 */
export async function importProjectBundle(api: ApiClient, bundle: ProjectBundle): Promise<BundleImportResult> {
  const project = bundle.project ?? {};
  const blocks = project.manuscript?.blocks ?? [];
  const sourceDrafterPages = Array.isArray(project.drafter?.pages)
    ? project.drafter!.pages
    : [];

  const res = await api.importWhiteboard({
    title: project.title ?? "",
    mode: project.mode ?? "novel",
    blocks,
    comments: project.comments ?? [],
  });
  const projectId = res.project_id;

  // Whiteboard owns a few voice/format controls Pro does not expose yet. Keep
  // the complete normalized payload in the new project's generic settings bag
  // so graduation is lossless and a future Pro control can adopt it.
  const sourceSettings = isRecord(project.settings) ? project.settings : null;
  let settingsImported = false;
  let settingsSkipped = false;
  let drafterArchivePreserved = sourceDrafterPages.length === 0;
  let drafterArchiveSkipped = false;
  if ((sourceSettings && Object.keys(sourceSettings).length) || sourceDrafterPages.length) {
    try {
      const current = await api.getSettings(projectId);
      const migratedSettings: Record<string, unknown> = {
        ...(isRecord(current.settings) ? current.settings : {}),
      };
      if (sourceSettings && Object.keys(sourceSettings).length) {
        migratedSettings.whiteboard_document_settings = { ...sourceSettings };
      }
      if (sourceDrafterPages.length) {
        // Keep the complete source representation in addition to the readable
        // Notes created below. A future Pro Drafter surface can adopt it without
        // reconstructing marks or screenplay metadata from plain text.
        migratedSettings.whiteboard_drafter_pages = sourceDrafterPages.map((page) => ({
          ...page,
          blocks: (page.blocks ?? []).map((block) => ({ ...block })),
        }));
      }
      await api.patchSettings(projectId, {
        settings: migratedSettings,
      });
      settingsImported = !!(sourceSettings && Object.keys(sourceSettings).length);
      drafterArchivePreserved = sourceDrafterPages.length > 0;
    } catch {
      settingsSkipped = !!(sourceSettings && Object.keys(sourceSettings).length);
      drafterArchiveSkipped = sourceDrafterPages.length > 0;
    }
  }

  let drafterPages = 0;
  let drafterPagesSkipped = 0;
  for (let index = 0; index < sourceDrafterPages.length; index += 1) {
    const page = sourceDrafterPages[index]!;
    const title = typeof page.title === "string" && page.title.trim()
      ? page.title.trim()
      : `Drafter page ${index + 1}`;
    try {
      await api.createNote(projectId, {
        title,
        content: drafterNoteContent(page),
        tags: ["whiteboard-drafter"],
        pinned: false,
      });
      drafterPages += 1;
    } catch {
      drafterPagesSkipped += 1;
    }
  }

  // Missing PSYKE collections are valid for older bundles. The parser rejects a
  // present non-array collection before this function creates the project.
  const elements = Array.isArray(project.psyke?.elements) ? project.psyke!.elements : [];
  const sourceRelations = Array.isArray(project.psyke?.relations) ? project.psyke!.relations : [];
  const sourceProgressions = Array.isArray(project.psyke?.progressions) ? project.psyke!.progressions : [];
  const hasCanonicalProgressionTracks = Object.prototype.hasOwnProperty.call(
    project,
    "progression_tracks",
  );
  const sourceProgressionTracks = Array.isArray(project.progression_tracks)
    ? project.progression_tracks
    : [];

  // New Whiteboard bundles carry both the canonical track snapshot and the
  // legacy per-entry projection for compatibility with old Pro releases. A
  // canonical compatibility track preserves the exact legacy beat ids and its
  // primary source entry. Import that track through createProgression so Core
  // can recreate its private legacy_psyke_entry_id linkage (including `other`
  // entries, whose canonical `custom + primary` shape cannot be created through
  // the public track command). All other canonical tracks use the command API.
  // When progression_tracks is present, unmatched legacy rows are stale
  // compatibility data and must not create duplicate beats.
  const legacyRowsByEntry = new Map<number, Array<{ index: number; id: number }>>();
  sourceProgressions.forEach((progression, index) => {
    const entryId = positiveSafeInteger(progression.entry_id);
    const id = positiveSafeInteger(progression.id);
    if (entryId == null || id == null) return;
    const rows = legacyRowsByEntry.get(entryId) ?? [];
    rows.push({ index, id });
    legacyRowsByEntry.set(entryId, rows);
  });
  const compatibilityTrackIndexes = new Set<number>();
  const compatibilityLegacyRowIndexes = new Set<number>();
  if (hasCanonicalProgressionTracks) {
    sourceProgressionTracks.forEach((track, trackIndex) => {
      const entryId = positiveSafeInteger(track.primary_psyke_entry_id);
      if (entryId == null || !Array.isArray(track.beats)) return;
      const beatIds = track.beats.map((beat) => positiveSafeInteger(beat.id));
      if (track.legacy_compatibility === true) {
        compatibilityTrackIndexes.add(trackIndex);
        const canonicalIds = new Set(beatIds.filter((id): id is number => id != null));
        (legacyRowsByEntry.get(entryId) ?? [])
          .filter((row) => canonicalIds.has(row.id))
          .forEach((row) => compatibilityLegacyRowIndexes.add(row.index));
        return;
      }
      // Marker-less bundles predate the explicit compatibility field. Retain
      // their exact non-empty beat-id projection as a narrow fallback, but an
      // explicit false marker is authoritative.
      if (track.legacy_compatibility === false || beatIds.length === 0 || beatIds.some((id) => id == null)) return;
      const uniqueBeatIds = new Set(beatIds as number[]);
      if (uniqueBeatIds.size !== beatIds.length) return;
      const legacyRows = legacyRowsByEntry.get(entryId) ?? [];
      if (legacyRows.length !== beatIds.length) return;
      if (!legacyRows.every((row) => uniqueBeatIds.has(row.id))) return;
      compatibilityTrackIndexes.add(trackIndex);
      legacyRows.forEach((row) => compatibilityLegacyRowIndexes.add(row.index));
    });
  }
  const sourceProgressionsForImport = hasCanonicalProgressionTracks
    ? sourceProgressions.filter((_progression, index) => compatibilityLegacyRowIndexes.has(index))
    : sourceProgressions;

  // An old id reused for different source entries cannot be mapped honestly.
  // Detect that before any writes so iteration order cannot choose a winner.
  const sourceEntryKeys = new Map<number, Set<string>>();
  for (const element of elements) {
    const oldId = sourceEntryId(element.id);
    if (oldId == null) continue;
    const keys = sourceEntryKeys.get(oldId) ?? new Set<string>();
    keys.add(entryKey(element));
    sourceEntryKeys.set(oldId, keys);
  }
  const ambiguousSourceEntryIds = new Set<number>();
  for (const [oldId, keys] of sourceEntryKeys) {
    if (keys.size > 1) ambiguousSourceEntryIds.add(oldId);
  }

  // The core's create is idempotent on (name, type). Dedupe on that exact,
  // case-sensitive key, but map every distinct, unambiguous source id carried by
  // duplicate rows to the already-created destination entry.
  const seen = new Set<string>();
  const destinationEntryByKey = new Map<string, number>();
  const destinationEntryBySourceId = new Map<number, number>();
  let entries = 0;
  let entriesSkipped = 0;
  for (const el of elements) {
    const name = typeof el?.name === "string" ? el.name.trim() : "";
    if (!name) { entriesSkipped += 1; continue; }   // a nameless entry can't be created
    const type = typeof el.entry_type === "string" && el.entry_type
      ? el.entry_type
      : "other";
    const key = entryKey(el);
    const oldId = sourceEntryId(el.id);
    if (seen.has(key)) {
      entriesSkipped += 1;
      const existingDestination = destinationEntryByKey.get(key);
      if (oldId != null && existingDestination != null &&
          !ambiguousSourceEntryIds.has(oldId)) {
        destinationEntryBySourceId.set(oldId, existingDestination);
      }
      continue;
    }
    seen.add(key);
    try {
      const created = await api.createPsyke(projectId, {
        name,
        type,
        aliases: Array.isArray(el.aliases) ? el.aliases : [],
        notes: typeof el.notes === "string" ? el.notes : "",
        details: typeof el.description === "string" && el.description
          ? { description: el.description }
          : {},
      });
      entries += 1;
      const destinationId = positiveSafeInteger(created.id);
      if (destinationId != null) {
        destinationEntryByKey.set(key, destinationId);
        if (oldId != null && !ambiguousSourceEntryIds.has(oldId)) {
          destinationEntryBySourceId.set(oldId, destinationId);
        }
      }
    } catch {
      entriesSkipped += 1;
      /* skip one bad element — keep migrating the rest */
    }
  }

  // Relations are canonical source DTOs, but their endpoint ids belong to the
  // old project. Remap both ends, reject collapsed/self edges, and keep only the
  // first row for an unordered destination pair. Calling createRelation with the
  // row's original source/target orientation preserves directional relation
  // semantics such as payoff ↔ supports_setup even if new numeric ids reorder.
  const destinationRelationPairs = new Set<string>();
  let relations = 0;
  let relationsSkipped = 0;
  for (const relation of sourceRelations) {
    const sourceId = positiveSafeInteger(relation.source_id);
    const targetId = positiveSafeInteger(relation.target_id);
    if (sourceId == null || targetId == null ||
        typeof relation.relation_type !== "string") {
      relationsSkipped += 1;
      continue;
    }
    const destinationSourceId = destinationEntryBySourceId.get(sourceId);
    const destinationTargetId = destinationEntryBySourceId.get(targetId);
    if (destinationSourceId == null || destinationTargetId == null ||
        destinationSourceId === destinationTargetId) {
      relationsSkipped += 1;
      continue;
    }
    const pair = destinationSourceId < destinationTargetId
      ? `${destinationSourceId}:${destinationTargetId}`
      : `${destinationTargetId}:${destinationSourceId}`;
    if (destinationRelationPairs.has(pair)) {
      relationsSkipped += 1;
      continue;
    }
    destinationRelationPairs.add(pair);
    try {
      await api.createRelation(projectId, {
        source_id: destinationSourceId,
        target_id: destinationTargetId,
        relation_type: relation.relation_type,
      });
      relations += 1;
    } catch {
      relationsSkipped += 1;
      /* preserve the first row's authority even when its API write fails */
    }
  }

  // ── Outline (Phase 2) + section↔scene links (Phase 3). Recreate the flat
  // Whiteboard tree as Pro outline nodes, parents first so each child's numeric
  // parent_id already exists. `idMap` maps the source string uuid → the created id.
  const outline = Array.isArray(project.outline) ? project.outline : [];
  const sourceIds = new Set<string>();
  let outlineDuplicateIds = 0;
  for (const node of outline) {
    if (node?.id == null) continue;
    const id = String(node.id);
    if (sourceIds.has(id)) outlineDuplicateIds += 1;
    else sourceIds.add(id);
  }

  // The Phase-1 import returns block index → scene id for outline links. Fetch
  // destination scenes exactly once when either those links need quote checking
  // or a progression carries a source scene anchor. The same snapshot serves
  // both import surfaces. If the read fails, outline links retain their existing
  // index-only fallback while progression beats are safely kept unanchored.
  const sceneIdsByBlock = Array.isArray(res.scene_ids_by_block) ? res.scene_ids_by_block : [];
  const anyLinks = outline.some((n) => n && n.link && typeof n.link.blockIndex === "number");
  const anyLinkedProgressions = sourceProgressionsForImport.some(
    (progression) => positiveSafeInteger(progression.scene_id) != null,
  ) || sourceProgressionTracks.some((track) => (track.beats ?? []).some(
    (beat) => beat.anchor_kind === "scene" && positiveSafeInteger(beat.scene_id) != null,
  ));
  const sceneTextById = new Map<number, string>();
  const destinationSceneIdsByTitle = new Map<string, number[]>();
  if (anyLinks || anyLinkedProgressions) {
    try {
      for (const s of await api.listScenes(projectId)) {
        sceneTextById.set(s.id, `${s.title ?? ""}\n${s.content ?? ""}`);
        const sceneId = positiveSafeInteger(s.id);
        const title = typeof s.title === "string" ? s.title.trim() : "";
        if (sceneId != null && title) {
          const ids = destinationSceneIdsByTitle.get(title) ?? [];
          ids.push(sceneId);
          destinationSceneIdsByTitle.set(title, ids);
        }
      }
    } catch { /* validation degrades to index-only resolution */ }
  }

  // One source scene id must describe one title. Conflicting titles make that
  // source id ambiguous even if either title happens to be unique in Pro.
  const sourceSceneTitles = new Map<number, Set<string>>();
  for (const progression of sourceProgressionsForImport) {
    const sourceSceneId = positiveSafeInteger(progression.scene_id);
    if (sourceSceneId == null) continue;
    const title = typeof progression.scene_title === "string"
      ? progression.scene_title.trim()
      : "";
    const titles = sourceSceneTitles.get(sourceSceneId) ?? new Set<string>();
    titles.add(title);
    sourceSceneTitles.set(sourceSceneId, titles);
  }
  for (const track of sourceProgressionTracks) {
    for (const beat of track.beats ?? []) {
      if (beat.anchor_kind !== "scene") continue;
      const sourceSceneId = positiveSafeInteger(beat.scene_id);
      if (sourceSceneId == null) continue;
      const title = typeof beat.scene_title === "string" ? beat.scene_title.trim() : "";
      const titles = sourceSceneTitles.get(sourceSceneId) ?? new Set<string>();
      titles.add(title);
      sourceSceneTitles.set(sourceSceneId, titles);
    }
  }
  const destinationSceneBySourceId = new Map<number, number | null>();
  for (const [sourceSceneId, titles] of sourceSceneTitles) {
    let destinationSceneId: number | null = null;
    if (titles.size === 1) {
      const title = titles.values().next().value as string;
      const candidates = title ? destinationSceneIdsByTitle.get(title) : undefined;
      if (candidates?.length === 1) destinationSceneId = candidates[0] ?? null;
    }
    destinationSceneBySourceId.set(sourceSceneId, destinationSceneId);
  }

  // The core assigns progression sort_order monotonically per entry. Process
  // valid source rows by entry/order/id so their relative arc order survives;
  // original array index is the deterministic final tie-break (and the fallback
  // when either optional source progression id is not a positive integer).
  const orderedProgressions = sourceProgressionsForImport
    .map((progression, index) => ({ progression, index }))
    .sort((left, right) => {
      const leftEntry = positiveSafeInteger(left.progression.entry_id);
      const rightEntry = positiveSafeInteger(right.progression.entry_id);
      if (leftEntry != null && rightEntry != null && leftEntry !== rightEntry) {
        return leftEntry < rightEntry ? -1 : 1;
      }
      if (leftEntry != null && rightEntry == null) return -1;
      if (leftEntry == null && rightEntry != null) return 1;

      const leftOrder = nonNegativeSafeInteger(left.progression.sort_order);
      const rightOrder = nonNegativeSafeInteger(right.progression.sort_order);
      if (leftOrder != null && rightOrder != null && leftOrder !== rightOrder) {
        return leftOrder < rightOrder ? -1 : 1;
      }
      if (leftOrder != null && rightOrder == null) return -1;
      if (leftOrder == null && rightOrder != null) return 1;

      const leftId = positiveSafeInteger(left.progression.id);
      const rightId = positiveSafeInteger(right.progression.id);
      if (leftId != null && rightId != null && leftId !== rightId) {
        return leftId < rightId ? -1 : 1;
      }
      return left.index - right.index;
    });

  let progressions = 0;
  let progressionsSkipped = 0;
  let progressionSceneLinks = 0;
  let progressionSceneLinksSkipped = 0;
  const createdLegacyBeatIdBySourceId = new Map<number, number>();
  for (const { progression } of orderedProgressions) {
    const sourceEntry = positiveSafeInteger(progression.entry_id);
    const sourceOrder = nonNegativeSafeInteger(progression.sort_order);
    const sourceScene = progression.scene_id == null
      ? null
      : positiveSafeInteger(progression.scene_id);
    if (sourceEntry == null || sourceOrder == null ||
        typeof progression.text !== "string" ||
        (progression.scene_id != null && sourceScene == null)) {
      if (!hasCanonicalProgressionTracks) progressionsSkipped += 1;
      continue;
    }
    const destinationEntry = destinationEntryBySourceId.get(sourceEntry);
    if (destinationEntry == null) {
      if (!hasCanonicalProgressionTracks) progressionsSkipped += 1;
      continue;
    }
    // Explicitly never reuse a source scene id. A null lookup means the source
    // title was absent, conflicting, missing, or non-unique in the new project.
    const destinationScene = sourceScene == null
      ? null
      : (destinationSceneBySourceId.get(sourceScene) ?? null);
    try {
      const created = await api.createProgression(projectId, {
        entry_id: destinationEntry,
        text: progression.text, // blank is valid in the core contract
        scene_id: destinationScene,
      });
      const sourceProgressionId = positiveSafeInteger(progression.id);
      const createdBeatId = positiveSafeInteger(created.id);
      if (sourceProgressionId != null && createdBeatId != null) {
        createdLegacyBeatIdBySourceId.set(sourceProgressionId, createdBeatId);
      }
      if (!hasCanonicalProgressionTracks) progressions += 1;
      if (!hasCanonicalProgressionTracks && sourceScene != null) {
        if (destinationScene != null) progressionSceneLinks += 1;
        else progressionSceneLinksSkipped += 1;
      }
    } catch (failure) {
      if (isAmbiguousBundleProgressionFailure(failure)) {
        throw new BundleProgressionDeliveryUncertainError(
          `A legacy PSYKE progression may have been created, but that endpoint has no durable receipt. Bundle import stopped without retrying it: ${failureMessage(failure)}`,
        );
      }
      if (!hasCanonicalProgressionTracks) progressionsSkipped += 1;
    }
  }

  // Reconcile the canonical section after PSYKE + scenes exist. Compatibility
  // tracks already have their rows through the legacy endpoint above; commands
  // now restore canonical presentation, rich anchors, and ordering without ever
  // attempting to mutate their protected kind/subject linkage. Ordinary tracks
  // are created directly through the revisioned command family.
  let progressionTracks = 0;
  let progressionTracksSkipped = 0;
  let progressionTrackBeats = 0;
  let progressionTrackBeatsSkipped = 0;
  let progressionTrackSceneLinks = 0;
  let progressionTrackSceneLinksSkipped = 0;
  let progressionSnapshot: ProgressionSnapshotDTO | null = null;
  if (sourceProgressionTracks.length) {
    try {
      api.invalidatePendingReads?.();
      progressionSnapshot = await api.getProgressions(projectId);
    } catch {
      progressionTracksSkipped = sourceProgressionTracks.length;
      progressionTrackBeatsSkipped = sourceProgressionTracks.reduce(
        (sum, track) => sum + (track.beats?.length ?? 0),
        0,
      );
    }
  }

  const orderedTracks = sourceProgressionTracks
    .map((track, index) => ({ track, index }))
    .sort((left, right) => {
      const leftOrder = nonNegativeSafeInteger(left.track.sort_order);
      const rightOrder = nonNegativeSafeInteger(right.track.sort_order);
      if (leftOrder != null && rightOrder != null && leftOrder !== rightOrder) return leftOrder - rightOrder;
      if (leftOrder != null && rightOrder == null) return -1;
      if (leftOrder == null && rightOrder != null) return 1;
      const leftId = positiveSafeInteger(left.track.id);
      const rightId = positiveSafeInteger(right.track.id);
      if (leftId != null && rightId != null && leftId !== rightId) return leftId - rightId;
      return left.index - right.index;
    });
  const orderedSourceBeats = (track: ProjectBundleProgressionTrack) => (track.beats ?? [])
    .map((beat, beatIndex) => ({ beat, beatIndex }))
    .sort((left, right) => {
      const leftOrder = nonNegativeSafeInteger(left.beat.sort_order);
      const rightOrder = nonNegativeSafeInteger(right.beat.sort_order);
      if (leftOrder != null && rightOrder != null && leftOrder !== rightOrder) return leftOrder - rightOrder;
      if (leftOrder != null && rightOrder == null) return -1;
      if (leftOrder == null && rightOrder != null) return 1;
      return left.beatIndex - right.beatIndex;
    });

  const destinationSubject = (
    sourceId: unknown,
    sourceName: unknown,
    sourceType: unknown,
  ): { id: number; type: string } | null => {
    const numericId = positiveSafeInteger(sourceId);
    const mapped = numericId == null ? undefined : destinationEntryBySourceId.get(numericId);
    const name = typeof sourceName === "string" ? sourceName.trim() : "";
    const type = typeof sourceType === "string" ? sourceType : "";
    const resolved = mapped ?? (name && type
      ? destinationEntryByKey.get(JSON.stringify([type, name]))
      : undefined);
    return resolved == null ? null : { id: resolved, type };
  };
  const resolveBeatAnchor = (beat: ProjectBundleProgressionBeat): {
    anchorKind: ProgressionAnchorKind;
    sceneId: number | null;
    anchorRef: string | null;
    anchorLabel: string;
    sceneRequested: boolean;
  } => {
    let anchorKind: ProgressionAnchorKind = beat.anchor_kind ?? "unanchored";
    let sceneId: number | null = null;
    let anchorRef: string | null = null;
    let anchorLabel = typeof beat.anchor_label === "string" ? beat.anchor_label : "";
    const sceneRequested = anchorKind === "scene";
    if (anchorKind === "scene") {
      const sourceSceneId = positiveSafeInteger(beat.scene_id);
      if (sourceSceneId != null) sceneId = destinationSceneBySourceId.get(sourceSceneId) ?? null;
      if (sceneId == null) {
        const titleKey = typeof beat.scene_title === "string" ? beat.scene_title.trim() : "";
        const candidates = titleKey ? destinationSceneIdsByTitle.get(titleKey) : undefined;
        if (candidates?.length === 1) sceneId = candidates[0] ?? null;
      }
      if (sceneId == null) {
        anchorKind = "unanchored";
        anchorLabel = "";
      }
    } else if (anchorKind === "document_block") {
      anchorRef = typeof beat.anchor_ref === "string" && beat.anchor_ref.trim()
        ? beat.anchor_ref.trim()
        : null;
      if (anchorRef == null) {
        anchorKind = "unanchored";
        anchorLabel = "";
      }
    }
    return { anchorKind, sceneId, anchorRef, anchorLabel, sceneRequested };
  };

  const destinationTrackIdBySourceIndex = new Map<number, number>();
  for (const { track, index: sourceTrackIndex } of orderedTracks) {
    if (!progressionSnapshot) break;
    const orderedBeats = orderedSourceBeats(track);
    if (compatibilityTrackIndexes.has(sourceTrackIndex)) {
      const destinationEntry = destinationSubject(
        track.primary_psyke_entry_id,
        track.primary_psyke_entry_name,
        track.primary_psyke_entry_type,
      );
      if (!destinationEntry) {
        progressionTracksSkipped += 1;
        progressionTrackBeatsSkipped += orderedBeats.length;
        continue;
      }
      const createdBeatIds: Array<number | null> = orderedBeats.map(({ beat }) => {
        const sourceBeatId = positiveSafeInteger(beat.id);
        return sourceBeatId == null ? null : createdLegacyBeatIdBySourceId.get(sourceBeatId) ?? null;
      });
      let compatibilityRowsAdded = false;
      for (let beatPosition = 0; beatPosition < orderedBeats.length; beatPosition += 1) {
        if (createdBeatIds[beatPosition] != null) continue;
        const { beat } = orderedBeats[beatPosition]!;
        if (typeof beat.text !== "string") continue;
        const anchor = resolveBeatAnchor(beat);
        try {
          const created = await api.createProgression(projectId, {
            entry_id: destinationEntry.id,
            text: beat.text,
            scene_id: anchor.anchorKind === "scene" ? anchor.sceneId : null,
          });
          const createdId = positiveSafeInteger(created.id);
          if (createdId != null) {
            createdBeatIds[beatPosition] = createdId;
            const sourceBeatId = positiveSafeInteger(beat.id);
            if (sourceBeatId != null) createdLegacyBeatIdBySourceId.set(sourceBeatId, createdId);
            compatibilityRowsAdded = true;
          }
        } catch (failure) {
          if (isAmbiguousBundleProgressionFailure(failure)) {
            throw new BundleProgressionDeliveryUncertainError(
              `A compatibility progression beat may have been created, but that legacy endpoint has no durable receipt. Bundle import stopped without retrying it: ${failureMessage(failure)}`,
            );
          }
          /* definitive failures are counted as a skipped canonical beat below */
        }
      }
      let temporaryEmptyBeatId: number | null = null;
      if (orderedBeats.length === 0) {
        try {
          const created = await api.createProgression(projectId, {
            entry_id: destinationEntry.id,
            text: "",
            scene_id: null,
          });
          temporaryEmptyBeatId = positiveSafeInteger(created.id);
          compatibilityRowsAdded = temporaryEmptyBeatId != null;
        } catch (failure) {
          if (isAmbiguousBundleProgressionFailure(failure)) {
            throw new BundleProgressionDeliveryUncertainError(
              `The temporary beat used to restore an empty compatibility track may have been created, but that legacy endpoint has no durable receipt. Bundle import stopped without retrying it: ${failureMessage(failure)}`,
            );
          }
          /* a definitive failure means the compatibility track cannot be materialized */
        }
      }
      if (compatibilityRowsAdded) {
        try {
          api.invalidatePendingReads?.();
          progressionSnapshot = await api.getProgressions(projectId);
        } catch {
          progressionTracksSkipped += 1;
          progressionTrackBeatsSkipped += orderedBeats.length;
          continue;
        }
      }
      const knownBeatIds = createdBeatIds.filter((id): id is number => id != null);
      if (temporaryEmptyBeatId != null) knownBeatIds.push(temporaryEmptyBeatId);
      const destinationTrack = progressionSnapshot.tracks.find((candidate) =>
        knownBeatIds.some((id) => candidate.beats.some((beat) => beat.id === id)),
      );
      if (!destinationTrack || knownBeatIds.some((id) => !destinationTrack.beats.some((beat) => beat.id === id))) {
        progressionTracksSkipped += 1;
        progressionTrackBeatsSkipped += orderedBeats.length;
        continue;
      }
      destinationTrackIdBySourceIndex.set(sourceTrackIndex, destinationTrack.id);
      const title = typeof track.title === "string" ? track.title.trim() : "";
      try {
        if (!title) throw new Error("Progression track title is blank.");
        progressionSnapshot = await executeBundleProgressionCommand(api, projectId, {
          kind: "update_track",
          expected_revision: progressionSnapshot.revision,
          track_id: destinationTrack.id,
          title,
          description: typeof track.description === "string" ? track.description : "",
          color_label: typeof track.color_label === "string" ? track.color_label : "",
        }, `lfbundle-progression-${projectId}-compat-track-${sourceTrackIndex}`);
        progressionTracks += 1;
      } catch (failure) {
        rethrowUncertainBundleProgression(failure);
        progressionTracksSkipped += 1;
      }

      for (let beatPosition = 0; beatPosition < orderedBeats.length; beatPosition += 1) {
        const { beat, beatIndex } = orderedBeats[beatPosition]!;
        const destinationBeatId = createdBeatIds[beatPosition] ?? null;
        if (destinationBeatId == null || typeof beat.text !== "string") {
          progressionTrackBeatsSkipped += 1;
          continue;
        }
        const anchor = resolveBeatAnchor(beat);
        if (anchor.sceneRequested && anchor.sceneId == null) progressionTrackSceneLinksSkipped += 1;
        try {
          progressionSnapshot = await executeBundleProgressionCommand(api, projectId, {
            kind: "update_beat",
            expected_revision: progressionSnapshot.revision,
            beat_id: destinationBeatId,
            ...(beat.text.trim() ? { text: beat.text } : {}),
            anchor_kind: anchor.anchorKind,
            scene_id: anchor.sceneId,
            anchor_ref: anchor.anchorRef,
            anchor_label: anchor.anchorLabel,
          }, `lfbundle-progression-${projectId}-compat-track-${sourceTrackIndex}-beat-${beatIndex}`);
          progressionTrackBeats += 1;
          if (anchor.sceneRequested && anchor.sceneId != null) progressionTrackSceneLinks += 1;
        } catch (failure) {
          rethrowUncertainBundleProgression(failure);
          progressionTrackBeatsSkipped += 1;
        }
      }

      const currentTrack = progressionSnapshot.tracks.find((candidate) => candidate.id === destinationTrack.id);
      if (currentTrack) {
        const desiredBeatIds = createdBeatIds.filter((id): id is number => id != null);
        const remainingBeatIds = [...currentTrack.beats]
          .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
          .map((beat) => beat.id)
          .filter((id) => !desiredBeatIds.includes(id));
        const exactBeatIds = [...desiredBeatIds, ...remainingBeatIds];
        const currentBeatIds = [...currentTrack.beats]
          .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
          .map((beat) => beat.id);
        if (exactBeatIds.length && exactBeatIds.some((id, index) => currentBeatIds[index] !== id)) {
          try {
            progressionSnapshot = await executeBundleProgressionCommand(api, projectId, {
              kind: "reorder_beats",
              expected_revision: progressionSnapshot.revision,
              track_id: destinationTrack.id,
              beat_ids: exactBeatIds,
            }, `lfbundle-progression-${projectId}-compat-track-${sourceTrackIndex}-reorder`);
          } catch (failure) {
            rethrowUncertainBundleProgression(failure);
            /* beat writes remain valid even if a definitive error blocked ordering */
          }
        }
      }
      if (temporaryEmptyBeatId != null) {
        try {
          progressionSnapshot = await executeBundleProgressionCommand(api, projectId, {
            kind: "delete_beat",
            expected_revision: progressionSnapshot.revision,
            beat_id: temporaryEmptyBeatId,
          }, `lfbundle-progression-${projectId}-compat-track-${sourceTrackIndex}-empty`);
        } catch (failure) {
          rethrowUncertainBundleProgression(failure);
          // Surface the imperfect empty-track reconstruction as a skipped item;
          // the linked track itself remains recoverable and editable.
          progressionTrackBeatsSkipped += 1;
        }
      }
      continue;
    }

    const kind = track.kind as ProgressionKind;
    const title = typeof track.title === "string" ? track.title.trim() : "";
    const primary = destinationSubject(
      track.primary_psyke_entry_id,
      track.primary_psyke_entry_name,
      track.primary_psyke_entry_type,
    );
    const secondary = destinationSubject(
      track.secondary_psyke_entry_id,
      track.secondary_psyke_entry_name,
      track.secondary_psyke_entry_type,
    );
    const sourceHasPrimary = track.primary_psyke_entry_id != null
      || !!track.primary_psyke_entry_name?.trim()
      || !!track.primary_psyke_entry_type?.trim();
    const sourceHasSecondary = track.secondary_psyke_entry_id != null
      || !!track.secondary_psyke_entry_name?.trim()
      || !!track.secondary_psyke_entry_type?.trim();
    const subjectsValid = kind === "story" || kind === "custom"
      ? !sourceHasPrimary && !sourceHasSecondary
      : kind === "character"
        ? primary?.type === "character" && secondary == null
        : kind === "theme"
          ? primary?.type === "theme" && secondary == null
          : kind === "world"
            ? primary != null && ["place", "object", "lore"].includes(primary.type) && secondary == null
            : kind === "relationship"
              ? primary != null && secondary != null && primary.id !== secondary.id
              : false;
    if (!title || !subjectsValid) {
      progressionTracksSkipped += 1;
      progressionTrackBeatsSkipped += orderedBeats.length;
      continue;
    }
    const priorTrackIds = new Set(progressionSnapshot.tracks.map((candidate) => candidate.id));
    try {
      progressionSnapshot = await executeBundleProgressionCommand(api, projectId, {
        kind: "create_track",
        expected_revision: progressionSnapshot.revision,
        track_kind: kind,
        title,
        description: typeof track.description === "string" ? track.description : "",
        color_label: typeof track.color_label === "string" ? track.color_label : "",
        primary_psyke_entry_id: kind === "story" || kind === "custom" ? null : primary?.id ?? null,
        secondary_psyke_entry_id: kind === "relationship" ? secondary?.id ?? null : null,
      }, `lfbundle-progression-${projectId}-track-${sourceTrackIndex}`);
    } catch (failure) {
      rethrowUncertainBundleProgression(failure);
      progressionTracksSkipped += 1;
      progressionTrackBeatsSkipped += orderedBeats.length;
      continue;
    }
    const createdTrack = progressionSnapshot.tracks.find((candidate) => !priorTrackIds.has(candidate.id));
    if (!createdTrack) {
      progressionTracksSkipped += 1;
      progressionTrackBeatsSkipped += orderedBeats.length;
      continue;
    }
    destinationTrackIdBySourceIndex.set(sourceTrackIndex, createdTrack.id);
    progressionTracks += 1;

    for (const { beat, beatIndex } of orderedBeats) {
      if (typeof beat.text !== "string") {
        progressionTrackBeatsSkipped += 1;
        continue;
      }
      const anchor = resolveBeatAnchor(beat);
      if (anchor.sceneRequested && anchor.sceneId == null) progressionTrackSceneLinksSkipped += 1;
      try {
        progressionSnapshot = await executeBundleProgressionCommand(api, projectId, {
          kind: "create_beat",
          expected_revision: progressionSnapshot.revision,
          track_id: createdTrack.id,
          text: beat.text,
          anchor_kind: anchor.anchorKind,
          scene_id: anchor.sceneId,
          anchor_ref: anchor.anchorRef,
          anchor_label: anchor.anchorLabel,
        }, `lfbundle-progression-${projectId}-track-${sourceTrackIndex}-beat-${beatIndex}`);
        progressionTrackBeats += 1;
        if (anchor.sceneRequested && anchor.sceneId != null) progressionTrackSceneLinks += 1;
      } catch (failure) {
        rethrowUncertainBundleProgression(failure);
        progressionTrackBeatsSkipped += 1;
      }
    }
  }

  // Legacy compatibility tracks are born in first-beat creation order. Restore
  // the source's single global track order after every track family is present.
  if (progressionSnapshot && destinationTrackIdBySourceIndex.size) {
    const desiredTrackIds = orderedTracks
      .map(({ index }) => destinationTrackIdBySourceIndex.get(index) ?? null)
      .filter((id): id is number => id != null);
    const remainingTrackIds = [...progressionSnapshot.tracks]
      .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
      .map((track) => track.id)
      .filter((id) => !desiredTrackIds.includes(id));
    const exactTrackIds = [...desiredTrackIds, ...remainingTrackIds];
    const currentTrackIds = [...progressionSnapshot.tracks]
      .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
      .map((track) => track.id);
    if (exactTrackIds.some((id, index) => currentTrackIds[index] !== id)) {
      try {
        progressionSnapshot = await executeBundleProgressionCommand(api, projectId, {
          kind: "reorder_tracks",
          expected_revision: progressionSnapshot.revision,
          track_ids: exactTrackIds,
        }, `lfbundle-progression-${projectId}-reorder-tracks`);
      } catch (failure) {
        rethrowUncertainBundleProgression(failure);
        /* imported tracks remain usable if a definitive error blocked ordering */
      }
    }
  }

  const idMap = new Map<string, number>();
  let outlineNodes = 0;
  let outlineSkipped = 0;
  let outlineReparented = 0;
  let links = 0;
  let linksSkipped = 0;
  for (const wb of topoSortOutline(outline)) {
    const pid = wb.parentId != null ? String(wb.parentId) : null;
    const parentId = pid != null ? (idMap.get(pid) ?? null) : null;
    if (pid != null && parentId == null) outlineReparented += 1;
    const hasLink = !!(wb.link && typeof wb.link.blockIndex === "number");
    const sceneId = hasLink ? resolveSceneLink(wb.link!, sceneIdsByBlock, sceneTextById) : null;
    try {
      const created = await api.createOutlineNode(projectId, {
        title: (wb.title ?? "").trim() || "Untitled",
        description: outlineDescription(wb),
        parent_id: parentId,   // missing/cyclic/failed parent → root
        sort_order: Number.isFinite(wb.order) ? (wb.order as number) : 0,   // NaN/Infinity → 0 (serialize to null → core 422)
        scene_id: sceneId,   // Phase 3: the reconstructed section↔scene hard link (or null)
      });
      if (wb.id != null) idMap.set(String(wb.id), created.id);
      outlineNodes += 1;
      if (hasLink) { if (sceneId != null) links += 1; else linksSkipped += 1; }
    } catch {
      outlineSkipped += 1;
      /* skip a bad node — its descendants fall back to the root via `?? null` */
      if (hasLink) linksSkipped += 1;   // its link couldn't be migrated
    }
  }

  // The core creates comment threads atomically with their replies while it still
  // has the authoritative block→scene/field/offset mapping.
  const comments = nonNegativeSafeInteger(res.comments_created) ?? 0;
  const commentsSkipped = nonNegativeSafeInteger(res.comments_skipped) ?? 0;
  const commentReplies = nonNegativeSafeInteger(res.comment_replies_created) ?? 0;
  const commentRepliesSkipped = nonNegativeSafeInteger(res.comment_replies_skipped) ?? 0;

  return {
    projectId,
    title: res.title,
    mode: res.mode,
    scenes: res.scenes_created,
    settingsImported,
    settingsSkipped,
    entries,
    entriesSkipped,
    relations,
    relationsSkipped,
    progressions,
    progressionsSkipped,
    progressionSceneLinks,
    progressionSceneLinksSkipped,
    progressionTracks,
    progressionTracksSkipped,
    progressionTrackBeats,
    progressionTrackBeatsSkipped,
    progressionTrackSceneLinks,
    progressionTrackSceneLinksSkipped,
    outlineNodes,
    outlineSkipped,
    outlineReparented,
    outlineDuplicateIds,
    comments,
    commentsSkipped,
    commentReplies,
    commentRepliesSkipped,
    drafterPages,
    drafterPagesSkipped,
    drafterArchivePreserved,
    drafterArchiveSkipped,
    links,
    linksSkipped,
  };
}
