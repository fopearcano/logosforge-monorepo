import type {
  ProjectDTO,
  ProjectSearchMatchDTO,
  PsykeConsoleCommandPlanDTO,
  PsykeConsoleExecutionDTO,
} from "@logosforge/ui-contracts";
import { normalizeCommandText } from "./search";
import {
  commandCategory,
  isCommandEnabled,
  type CommandDescriptor,
  type CommandRegistry,
} from "./types";
import type { StudioNavigationOptions } from "../adapters/StudioProvider";

export const OMNIBOX_GROUP_ORDER = [
  "Commands",
  "Panels",
  "Scenes",
  "Notes",
  "PSYKE",
  "Comments",
  "Projects",
] as const;

export type OmniboxGroup = typeof OMNIBOX_GROUP_ORDER[number];
export type OmniboxTargetKind = "command" | "panel" | "scene" | "note" | "psyke" | "comment" | "project";

interface OmniboxItemBase {
  readonly key: string;
  readonly kind: OmniboxTargetKind;
  readonly group: OmniboxGroup;
  readonly label: string;
  readonly detail: string;
  readonly keywords: readonly string[];
  readonly shortcut?: string;
  readonly disabled: boolean;
  readonly showWhenEmpty: boolean;
  /** A small deterministic boost, never large enough to cross match classes. */
  readonly priority: number;
  /**
   * Position assigned by the authoritative project-search API. Server-backed
   * results have already been matched and ranked (including Unicode casefold
   * behavior the lightweight client matcher cannot reproduce), so consumers
   * must preserve this order within their result group.
   */
  readonly authoritativeRank?: number;
}

export type OmniboxItem =
  | (OmniboxItemBase & { readonly kind: "command"; readonly commandId: string })
  | (OmniboxItemBase & { readonly kind: "panel"; readonly panelId: string })
  | (OmniboxItemBase & { readonly kind: "scene"; readonly sceneId: number })
  | (OmniboxItemBase & { readonly kind: "note"; readonly noteId: number })
  | (OmniboxItemBase & { readonly kind: "psyke"; readonly psykeEntryId: number })
  | (OmniboxItemBase & { readonly kind: "comment"; readonly commentId: number })
  | (OmniboxItemBase & { readonly kind: "project"; readonly projectId: number });

export interface OmniboxPanel {
  readonly id: string;
  readonly label: string;
  readonly keywords?: readonly string[];
  readonly shortcut?: string;
}

export interface OmniboxSources {
  readonly commands: readonly CommandDescriptor[];
  readonly panels: readonly OmniboxPanel[];
  readonly projects: readonly ProjectDTO[];
  readonly recentProjectIds: readonly number[];
  readonly activeProjectId?: number;
  readonly projectMatches: readonly ProjectSearchMatchDTO[];
}

export interface OmniboxSection {
  readonly group: OmniboxGroup;
  readonly items: readonly OmniboxItem[];
}

export interface OmniboxSearchOptions {
  readonly perGroupLimit?: number;
  readonly totalLimit?: number;
}

function uniqueText(values: readonly (string | undefined)[]): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const normalized = normalizeCommandText(value ?? "");
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(value!.trim());
  }
  return result;
}

function projectMode(project: ProjectDTO): string {
  return project.narrative_engine || project.format_mode || project.default_writing_format || "project";
}

function assertUniqueOmniboxKeys(items: readonly OmniboxItem[]): void {
  const seen = new Set<string>();
  for (const item of items) {
    if (seen.has(item.key)) throw new Error(`Duplicate omnibox item key: ${item.key}`);
    seen.add(item.key);
  }
}

/** Build stable, action-free search records from authoritative host/API data. */
export function buildOmniboxItems(sources: OmniboxSources): readonly OmniboxItem[] {
  const recentRank = new Map(sources.recentProjectIds.map((id, index) => [id, index]));
  const items: OmniboxItem[] = [];

  for (const command of sources.commands) {
    if (command.showInOmnibox === false) continue;
    items.push({
      key: `command:${command.id}`,
      kind: "command",
      group: "Commands",
      commandId: command.id,
      label: command.label,
      detail: commandCategory(command),
      keywords: uniqueText([command.id, ...(command.aliases ?? []), ...(command.keywords ?? [])]),
      shortcut: command.shortcut,
      disabled: !isCommandEnabled(command),
      showWhenEmpty: true,
      priority: 0,
    });
  }

  for (const panel of sources.panels) {
    items.push({
      key: `panel:${panel.id}`,
      kind: "panel",
      group: "Panels",
      panelId: panel.id,
      label: panel.label,
      detail: "Open workspace panel",
      keywords: uniqueText([panel.id, ...(panel.keywords ?? []), "workspace", "panel"]),
      shortcut: panel.shortcut,
      disabled: false,
      showWhenEmpty: true,
      priority: 0,
    });
  }

  for (const [authoritativeRank, match] of sources.projectMatches.entries()) {
    if (match.kind === "scene") {
      items.push({
        key: `scene:${match.id}`,
        kind: "scene",
        group: "Scenes",
        sceneId: match.id,
        label: match.title || `Scene ${match.id}`,
        detail: match.excerpt || "Open in Manuscript",
        keywords: uniqueText([String(match.id), match.title, match.excerpt]),
        disabled: false,
        showWhenEmpty: false,
        priority: 0,
        authoritativeRank,
      });
    } else if (match.kind === "note") {
      items.push({
        key: `note:${match.id}`,
        kind: "note",
        group: "Notes",
        noteId: match.id,
        label: match.title || `Note ${match.id}`,
        detail: match.excerpt || "Open in Notes",
        keywords: uniqueText([String(match.id), match.title, match.excerpt]),
        disabled: false,
        showWhenEmpty: false,
        priority: 0,
        authoritativeRank,
      });
    } else if (match.kind === "psyke") {
      items.push({
        key: `psyke:${match.id}`,
        kind: "psyke",
        group: "PSYKE",
        psykeEntryId: match.id,
        label: match.title || `PSYKE entry ${match.id}`,
        detail: match.excerpt || "Story bible entry",
        keywords: uniqueText([String(match.id), match.title, match.excerpt]),
        disabled: false,
        showWhenEmpty: false,
        priority: 0,
        authoritativeRank,
      });
    } else if (match.kind === "comment") {
      const status = match.resolved ? "Resolved" : "Open";
      items.push({
        key: `comment:${match.id}`,
        kind: "comment",
        group: "Comments",
        commentId: match.id,
        label: match.title || `Comment ${match.id}`,
        detail: match.excerpt ? `${status} · ${match.excerpt}` : `${status} comment thread`,
        keywords: uniqueText([String(match.id), match.title, match.excerpt, status, match.revision ?? undefined]),
        disabled: false,
        showWhenEmpty: false,
        priority: 0,
        authoritativeRank,
      });
    }
  }

  for (const project of sources.projects) {
    const recentIndex = recentRank.get(project.id);
    const active = project.id === sources.activeProjectId;
    const recent = recentIndex !== undefined;
    items.push({
      key: `project:${project.id}`,
      kind: "project",
      group: "Projects",
      projectId: project.id,
      label: project.title || `Project ${project.id}`,
      detail: `${active ? "Current" : recent ? "Recent" : "Project"} · ${projectMode(project)}`,
      keywords: uniqueText([String(project.id), project.title, project.description, projectMode(project), "project"]),
      disabled: active,
      showWhenEmpty: recent,
      priority: active ? 80 : recent ? Math.max(1, 60 - recentIndex * 5) : 0,
    });
  }

  assertUniqueOmniboxKeys(items);
  return items;
}

function subsequenceScore(needle: string, haystack: string): number | null {
  let needleIndex = 0;
  let first = -1;
  let last = -1;
  for (let index = 0; index < haystack.length && needleIndex < needle.length; index += 1) {
    if (haystack[index] !== needle[needleIndex]) continue;
    if (first < 0) first = index;
    last = index;
    needleIndex += 1;
  }
  if (needleIndex !== needle.length) return null;
  return Math.max(1, 1_000 - (last - first + 1 - needle.length) * 8 - first * 2);
}

function scoreField(query: string, rawValue: string, weight: number): number | null {
  const value = normalizeCommandText(rawValue);
  if (!value) return null;
  if (value === query) return 5_000 + weight;
  if (value.startsWith(query)) return 4_000 + weight - Math.min(200, value.length - query.length);
  const wordIndex = value.split(/[^a-z0-9]+/).findIndex((word) => word.startsWith(query));
  if (wordIndex >= 0) return 3_000 + weight - wordIndex;
  const substringIndex = value.indexOf(query);
  if (substringIndex >= 0) return 2_000 + weight - Math.min(500, substringIndex);
  const fuzzy = subsequenceScore(query.replace(/\s/g, ""), value.replace(/\s/g, ""));
  return fuzzy == null ? null : fuzzy + weight;
}

function itemScore(item: OmniboxItem, query: string): number | null {
  const fields: Array<readonly [string, number]> = [
    [item.label, 90],
    [item.detail, 30],
    [item.group, 20],
    ...item.keywords.map((keyword) => [keyword, 55] as const),
  ];
  let best = -1;
  for (const [value, weight] of fields) {
    const score = scoreField(query, value, weight);
    if (score != null) best = Math.max(best, score);
  }
  if (best >= 0) return best + item.priority;

  const terms = query.split(" ").filter(Boolean);
  if (terms.length < 2) return null;
  let total = 0;
  for (const term of terms) {
    let termBest = -1;
    for (const [value, weight] of fields) {
      const score = scoreField(term, value, weight);
      if (score != null) termBest = Math.max(termBest, score);
    }
    if (termBest < 0) return null;
    total += termBest;
  }
  return Math.round(total / terms.length) + item.priority;
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

/** Search, rank, cap, and group results independently of input ordering. */
export function searchOmniboxItems(
  items: readonly OmniboxItem[],
  query: string,
  options: OmniboxSearchOptions = {},
): readonly OmniboxSection[] {
  const normalized = normalizeCommandText(query);
  const perGroupLimit = Math.max(1, options.perGroupLimit ?? 8);
  // Keep the default large enough that every group can reach its own cap.
  // Otherwise adding a later entity group (notably Comments) silently starves
  // it when earlier groups are full.
  const totalLimit = Math.max(1, options.totalLimit ?? perGroupLimit * OMNIBOX_GROUP_ORDER.length);
  const ranked = items.flatMap((item, inputIndex) => {
    if (!normalized) return item.showWhenEmpty ? [{ item, score: item.priority, inputIndex }] : [];
    // Project-search results are already authoritative matches. Keeping them
    // avoids dropping server-only Unicode casefold matches (for example,
    // STRASSE -> Straße) and their rank is handled directly below.
    if (item.authoritativeRank != null) return [{ item, score: 0, inputIndex }];
    const score = itemScore(item, normalized);
    return score == null ? [] : [{ item, score, inputIndex }];
  });
  ranked.sort((left, right) => {
    const groupOrder = OMNIBOX_GROUP_ORDER.indexOf(left.item.group)
      - OMNIBOX_GROUP_ORDER.indexOf(right.item.group);
    if (groupOrder !== 0) return groupOrder;
    if (
      left.item.authoritativeRank != null
      && right.item.authoritativeRank != null
    ) {
      const authoritativeOrder = left.item.authoritativeRank - right.item.authoritativeRank;
      if (authoritativeOrder !== 0) return authoritativeOrder;
    }
    return right.score - left.score
      || compareText(normalizeCommandText(left.item.label), normalizeCommandText(right.item.label))
      || compareText(left.item.key, right.item.key)
      || left.inputIndex - right.inputIndex;
  });

  let remaining = totalLimit;
  const sections: OmniboxSection[] = [];
  for (const group of OMNIBOX_GROUP_ORDER) {
    if (remaining <= 0) break;
    const groupItems = ranked
      .filter((entry) => entry.item.group === group)
      .slice(0, Math.min(perGroupLimit, remaining))
      .map((entry) => entry.item);
    if (groupItems.length === 0) continue;
    sections.push({ group, items: groupItems });
    remaining -= groupItems.length;
  }
  return sections;
}

export function flattenOmniboxSections(sections: readonly OmniboxSection[]): readonly OmniboxItem[] {
  return sections.flatMap((section) => section.items);
}

export function firstEnabledOmniboxIndex<T extends { readonly disabled: boolean }>(items: readonly T[]): number {
  return items.findIndex((item) => !item.disabled);
}

/** Wrap through enabled options; -1 means no runnable option exists. */
export function moveOmniboxSelection(
  items: readonly { readonly disabled: boolean }[],
  currentIndex: number,
  direction: 1 | -1,
): number {
  if (items.length === 0 || items.every((item) => item.disabled)) return -1;
  let index = currentIndex >= 0 && currentIndex < items.length
    ? currentIndex
    : direction > 0 ? -1 : 0;
  for (let attempts = 0; attempts < items.length; attempts += 1) {
    index = (index + direction + items.length) % items.length;
    if (!items[index]!.disabled) return index;
  }
  return -1;
}

export function omniboxOptionDomId(prefix: string, key: string): string {
  let hash = 2_166_136_261;
  for (let index = 0; index < key.length; index += 1) {
    hash ^= key.charCodeAt(index);
    hash = Math.imul(hash, 16_777_619);
  }
  const readable = key.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48);
  return `${prefix}-option-${readable || "item"}-${(hash >>> 0).toString(36)}`;
}

export function parseRecentProjectIds(raw: string | null, limit = 6): readonly number[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const result: number[] = [];
    for (const value of parsed) {
      const id = Number(value);
      if (!Number.isInteger(id) || id <= 0 || result.includes(id)) continue;
      result.push(id);
      if (result.length >= limit) break;
    }
    return result;
  } catch {
    return [];
  }
}

export function rememberRecentProject(
  current: readonly number[],
  projectId: number,
  limit = 6,
): readonly number[] {
  if (!Number.isInteger(projectId) || projectId <= 0) return [...current];
  return [projectId, ...current.filter((id) => id !== projectId)].slice(0, Math.max(1, limit));
}

export interface OmniboxActivationContext {
  flush(): Promise<void>;
  registry: CommandRegistry;
  navigate(panel: string, options?: StudioNavigationOptions): void | boolean | Promise<void | boolean>;
  selectProject(projectId: number): Promise<boolean>;
}

/** Execute one resolved target only after the shared project save barrier. */
export async function activateOmniboxItem(
  item: OmniboxItem,
  context: OmniboxActivationContext,
): Promise<boolean> {
  if (item.disabled) return false;
  await context.flush();
  let result: unknown;
  switch (item.kind) {
    case "command": result = await context.registry.execute(item.commandId); break;
    case "panel": result = await context.navigate(item.panelId); break;
    case "scene": result = await context.navigate("manuscript", { sceneId: item.sceneId }); break;
    case "note": result = await context.navigate("notes", { noteId: item.noteId }); break;
    case "psyke": result = await context.navigate("psyke", { psykeEntryId: item.psykeEntryId }); break;
    case "comment": result = await context.navigate("comments", { commentId: item.commentId }); break;
    case "project": result = await context.selectProject(item.projectId); break;
  }
  return result !== false;
}

export interface OmniboxPlanOwner {
  readonly projectId: number;
  readonly sceneId: number | null;
  readonly planId: string;
}

export interface OmniboxPlanIdentity {
  readonly projectId: number | undefined;
  readonly sceneId: number | null;
}

export class StaleOmniboxPlanError extends Error {
  constructor() {
    super("The command preview is stale. Preview it again before running it.");
    this.name = "StaleOmniboxPlanError";
  }
}

function planOwnerMatches(owner: OmniboxPlanOwner, identity: OmniboxPlanIdentity): boolean {
  return owner.projectId === identity.projectId && owner.sceneId === identity.sceneId;
}

/** Revalidate the plan both before and after the asynchronous save barrier. */
export async function executeOmniboxPlan({
  plan,
  owner,
  getIdentity,
  flush,
  execute,
}: {
  plan: PsykeConsoleCommandPlanDTO;
  owner: OmniboxPlanOwner;
  getIdentity(): OmniboxPlanIdentity;
  flush(): Promise<void>;
  execute(projectId: number, planId: string, mutates: boolean): Promise<PsykeConsoleExecutionDTO>;
}): Promise<PsykeConsoleExecutionDTO> {
  if (owner.planId !== plan.plan_id || !planOwnerMatches(owner, getIdentity())) {
    throw new StaleOmniboxPlanError();
  }
  await flush();
  if (!planOwnerMatches(owner, getIdentity())) throw new StaleOmniboxPlanError();
  return execute(owner.projectId, owner.planId, plan.mutates);
}
