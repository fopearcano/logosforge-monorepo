import type { WhiteboardImportBlockDTO } from "@logosforge/ui-contracts";
import type { ApiClient } from "./api";

/**
 * A LogosForge project bundle (`.lfbundle`) — the single-project migration
 * artifact exported by Whiteboard (File → Export → Export Project). One bundle
 * carries a whole project: manuscript blocks + the PSYKE story bible (imported
 * here in Phase 1) plus, for a later phase, the manual outline and inline
 * comments. The format is a fixed contract owned by the Whiteboard exporter —
 * this module only READS it and orchestrates existing Pro endpoints.
 */
export interface ProjectBundlePsykeElement {
  id?: string;
  name?: string;
  entry_type?: string;      // character | place | object | lore | theme | other
  aliases?: string[];
  description?: string;     // free text; Whiteboard round-trips it via details.description
  notes?: string;
}

/** A Whiteboard manual-outline node. Flat list; the tree is `parentId` + `order`.
 * Richer than Pro's node (which has only title/description/parent/sort_order), so
 * the extra metadata is folded into the imported node's description. */
export interface ProjectBundleOutlineNode {
  id?: string;
  parentId?: string | null;
  type?: string;            // act | part | chapter | sequence | scene | beat | custom
  title?: string;
  order?: number;
  status?: string;          // none | todo | drafting | done | …
  colorLabel?: string;      // none | blue | green | …
  tags?: string[];
  completed?: boolean;
  // Phase 3 — optional hard link to a manuscript block ("this node owns the
  // manuscript from here"). `blockIndex` is 0-based into project.manuscript.blocks;
  // `quote` is a snapshot of that block's text, used as a re-anchor sanity check.
  link?: { blockIndex: number; quote?: string } | null;
}

export interface ProjectBundle {
  format?: string;
  version?: string;
  project?: {
    id?: string;
    title?: string;
    mode?: string;          // novel | screenplay | scene | graphic_novel | stage_script
    manuscript?: { blocks?: WhiteboardImportBlockDTO[] };
    psyke?: { elements?: ProjectBundlePsykeElement[] };
    outline?: ProjectBundleOutlineNode[];   // Phase 2 — imported
    comments?: unknown[];   // carried by the bundle; DEFERRED (Pro has no inline comments)
  };
}

export interface BundleImportResult {
  projectId: number;
  title: string;
  mode: string;
  scenes: number;
  entries: number;          // PSYKE bible entries created
  outlineNodes: number;     // outline nodes recreated (Phase 2)
  comments: number;         // comments the bundle carries but that were NOT migrated (deferred)
  links: number;            // outline→scene hard links reconstructed (Phase 3)
  linksSkipped: number;     // outline nodes that carried a link that couldn't be resolved
}

export const BUNDLE_FORMAT = "logosforge-project-bundle";

/**
 * Parse + validate a `.lfbundle`'s text. Throws a user-facing `Error` on bad
 * JSON or a file that isn't a project bundle. Tolerant of a future `version`
 * bump (same top-level shape) and of a missing outline/comments/psyke (older or
 * smaller bundles — treated as empty).
 */
export function parseProjectBundle(text: string): ProjectBundle {
  let bundle: ProjectBundle;
  try {
    bundle = JSON.parse(text) as ProjectBundle;
  } catch {
    throw new Error("That file isn't valid JSON.");
  }
  if (!bundle || bundle.format !== BUNDLE_FORMAT) {
    throw new Error("That isn't a LogosForge project bundle (.lfbundle).");
  }
  if (!bundle.project) {
    throw new Error("This bundle has no project data.");
  }
  return bundle;
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

/**
 * Import a `.lfbundle` into ONE new Pro project — client-side orchestration over
 * existing endpoints, no core change:
 *   1. Manuscript → reuse the blocks→scenes converter via `api.importWhiteboard`,
 *      which creates the new project (mode-correct) and returns its id.
 *   2. PSYKE → loop the bible elements into that project via `api.createPsyke`,
 *      mapping the bundle's frontend shape (`entry_type`, free-text
 *      `description`) back onto the core entry (`type`, and
 *      `details.description` — the same slot Whiteboard round-trips it in, which
 *      Pro's PSYKE overview renders).
 *   3. OUTLINE (Phase 2) → recreate the manual outline via `api.createOutlineNode`,
 *      topologically (parents first), remapping the string parentId → the new
 *      numeric parent_id and folding Whiteboard's type/status/colour/tags into
 *      the description. The project is freshly created so its outline is empty →
 *      we append; each create fires `outline_changed` so the panel refreshes.
 *      SECTION↔SCENE LINK (Phase 3) → if a node carries `link.blockIndex`, resolve
 *      it to a scene id via the import's `scene_ids_by_block` map (quote-validated)
 *      and set the node's `scene_id`, so the "this section lives here" association
 *      survives. Unresolvable links are skipped and counted.
 *   4. COMMENTS → DEFERRED. Pro has no inline-comments subsystem, and Whiteboard's
 *      are span-anchored — no honest 1:1 target. We carry the COUNT so the caller
 *      can report "N not migrated"; the comments stay in the bundle for a future
 *      span-level import.
 *
 * A single failing bible/outline entry is skipped, not fatal. A failure in
 * step 1 propagates (no project should exist without its manuscript); the caller
 * reports it and nothing partial is opened.
 */
export async function importProjectBundle(api: ApiClient, bundle: ProjectBundle): Promise<BundleImportResult> {
  const project = bundle.project ?? {};
  const blocks = project.manuscript?.blocks ?? [];

  const res = await api.importWhiteboard({
    title: project.title ?? "",
    mode: project.mode ?? "novel",
    blocks,
  });
  const projectId = res.project_id;

  // `elements` may be absent or, in a hand-edited/corrupt bundle, not an array —
  // guard it (like `aliases` below) so a bad shape degrades to an empty import
  // instead of throwing after the project + scenes were already created.
  const elements = Array.isArray(project.psyke?.elements) ? project.psyke!.elements : [];
  // The core's create is idempotent on (name, type) — a bundle that carried the
  // same entry twice would otherwise fire redundant no-op creates and inflate the
  // count. Dedupe on the same (case-sensitive) key the core uses.
  const seen = new Set<string>();
  let entries = 0;
  for (const el of elements) {
    const name = el?.name?.trim();
    if (!name) continue;   // a nameless entry can't be created
    const type = el.entry_type || "other";
    const key = `${type} ${name}`;
    if (seen.has(key)) continue;
    seen.add(key);
    try {
      await api.createPsyke(projectId, {
        name,
        type,
        aliases: Array.isArray(el.aliases) ? el.aliases : [],
        notes: el.notes ?? "",
        details: el.description ? { description: el.description } : {},
      });
      entries += 1;
    } catch {
      /* skip one bad element — keep migrating the rest */
    }
  }

  // ── Outline (Phase 2) + section↔scene links (Phase 3). Recreate the flat
  // Whiteboard tree as Pro outline nodes, parents first so each child's numeric
  // parent_id already exists. `idMap` maps the source string uuid → the created id.
  const outline = Array.isArray(project.outline) ? project.outline : [];

  // Phase 3: the Phase-1 import returns block index → scene id; a node's `link`
  // (blockIndex + quote) resolves to the scene it now lives in. Fetch the scene
  // texts once (only if any node is linked) for the quote sanity check.
  const sceneIdsByBlock = Array.isArray(res.scene_ids_by_block) ? res.scene_ids_by_block : [];
  const anyLinks = outline.some((n) => n && n.link && typeof n.link.blockIndex === "number");
  const sceneTextById = new Map<number, string>();
  if (anyLinks) {
    try {
      for (const s of await api.listScenes(projectId)) {
        sceneTextById.set(s.id, `${s.title ?? ""}\n${s.content ?? ""}`);
      }
    } catch { /* validation degrades to index-only resolution */ }
  }

  const idMap = new Map<string, number>();
  let outlineNodes = 0;
  let links = 0;
  let linksSkipped = 0;
  for (const wb of topoSortOutline(outline)) {
    const pid = wb.parentId != null ? String(wb.parentId) : null;
    const hasLink = !!(wb.link && typeof wb.link.blockIndex === "number");
    const sceneId = hasLink ? resolveSceneLink(wb.link!, sceneIdsByBlock, sceneTextById) : null;
    try {
      const created = await api.createOutlineNode(projectId, {
        title: (wb.title ?? "").trim() || "Untitled",
        description: foldOutlineMeta(wb),
        parent_id: pid != null ? (idMap.get(pid) ?? null) : null,   // missing/cyclic parent → root
        sort_order: Number.isFinite(wb.order) ? (wb.order as number) : 0,   // NaN/Infinity → 0 (serialize to null → core 422)
        scene_id: sceneId,   // Phase 3: the reconstructed section↔scene hard link (or null)
      });
      if (wb.id != null) idMap.set(String(wb.id), created.id);
      outlineNodes += 1;
      if (hasLink) { if (sceneId != null) links += 1; else linksSkipped += 1; }
    } catch {
      /* skip a bad node — its descendants fall back to the root via `?? null` */
      if (hasLink) linksSkipped += 1;   // its link couldn't be migrated
    }
  }

  // ── Comments: DEFERRED (see the function doc) — carry only the count.
  const comments = Array.isArray(project.comments) ? project.comments.length : 0;

  return { projectId, title: res.title, mode: res.mode, scenes: res.scenes_created, entries, outlineNodes, comments, links, linksSkipped };
}
