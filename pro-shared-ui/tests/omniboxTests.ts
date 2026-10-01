import type {
  ProjectDTO,
  ProjectSearchMatchDTO,
  PsykeConsoleCommandPlanDTO,
} from "@logosforge/ui-contracts";
import {
  OMNIBOX_GROUP_ORDER,
  StaleOmniboxPlanError,
  activateOmniboxItem,
  buildOmniboxItems,
  createCommandRegistry,
  executeOmniboxPlan,
  firstEnabledOmniboxIndex,
  flattenOmniboxSections,
  moveOmniboxSelection,
  omniboxOptionDomId,
  parseRecentProjectIds,
  rememberRecentProject,
  searchOmniboxItems,
  type CommandDescriptor,
  type OmniboxItem,
} from "../src";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: unknown): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const project = (id: number, title: string): ProjectDTO => ({
  id,
  title,
  description: `${title} project description`,
  narrative_engine: "novel",
  default_writing_format: "novel",
  format_mode: "novel",
});
const match = (
  kind: ProjectSearchMatchDTO["kind"],
  id: number,
  title: string,
  excerpt = "",
  metadata: Pick<ProjectSearchMatchDTO, "revision" | "resolved"> = {},
): ProjectSearchMatchDTO => ({ kind, id, title, excerpt, ...metadata });

const calls: string[] = [];
const commands: CommandDescriptor[] = [
  { id: "new-project", category: "Project", label: "New project", keywords: ["alpha"], run: () => calls.push("command") },
  { id: "disabled", category: "View", label: "Disabled alpha command", enabled: false, run: () => calls.push("disabled") },
  { id: "menu-only", category: "Native", label: "Hidden native item", showInOmnibox: false, run: () => undefined },
];
const registry = createCommandRegistry(commands);
const sources = {
  commands: registry.list(),
  panels: [{ id: "manuscript", label: "Alpha Manuscript", keywords: ["editor"] }],
  projects: [project(1, "Alpha Current"), project(2, "Alpha Recent"), project(3, "Alpha Archive")],
  recentProjectIds: [2, 1],
  activeProjectId: 1,
  projectMatches: [
    match("scene", 10, "Alpha Scene", "The opening"),
    match("psyke", 20, "Alpha Hero", "character"),
    match("note", 30, "Alpha Note", "A searchable note excerpt"),
    match("comment", 40, "Alpha Comment", "A searchable resolved comment", {
      revision: "4".repeat(64),
      resolved: true,
    }),
  ],
};
const items = buildOmniboxItems(sources);

check("build creates stable discriminated keys", ["command:new-project", "panel:manuscript", "scene:10", "note:30", "psyke:20", "comment:40", "project:2"].every((key) => items.some((item) => item.key === key)));
check("menu-only commands are excluded", !items.some((item) => item.key === "command:menu-only"));
check("disabled commands remain searchable", items.find((item) => item.key === "command:disabled")?.disabled === true);
check("current project is non-runnable", items.find((item) => item.key === "project:1")?.disabled === true);
check("recent project is marked for empty-query display", items.find((item) => item.key === "project:2")?.showWhenEmpty === true);
check("non-recent project is hidden from empty-query display", items.find((item) => item.key === "project:3")?.showWhenEmpty === false);
const noteItem = items.find((item) => item.key === "note:30");
const commentItem = items.find((item) => item.key === "comment:40");
check("note results expose their direct target id", noteItem?.kind === "note" && noteItem.noteId === 30);
check("comment results expose their direct target id", commentItem?.kind === "comment" && commentItem.commentId === 40);

const alphaSections = searchOmniboxItems(items, "alpha");
check("groups use canonical order", alphaSections.map((section) => section.group).join(",") === OMNIBOX_GROUP_ORDER.join(","));
check("flatten includes searchable note and comment targets", ["note:30", "comment:40"].every((key) => flattenOmniboxSections(alphaSections).some((item) => item.key === key)));
const emptyItems = flattenOmniboxSections(searchOmniboxItems(items, ""));
check("empty query includes commands", emptyItems.some((item) => item.kind === "command"));
check("empty query includes panels", emptyItems.some((item) => item.kind === "panel"));
check("empty query includes recent projects", emptyItems.some((item) => item.kind === "project" && item.projectId === 2));
check("empty query excludes scenes", !emptyItems.some((item) => item.kind === "scene"));
check("empty query excludes notes", !emptyItems.some((item) => item.kind === "note"));
check("empty query excludes PSYKE", !emptyItems.some((item) => item.kind === "psyke"));
check("empty query excludes comments", !emptyItems.some((item) => item.kind === "comment"));
check("empty query excludes non-recent projects", !emptyItems.some((item) => item.kind === "project" && item.projectId === 3));

const rankItems = buildOmniboxItems({
  commands: [], panels: [], projects: [], recentProjectIds: [],
  projectMatches: [
    match("scene", 5, "a-x-b-y-c"),
    match("scene", 4, "xabc"),
    match("scene", 3, "The abc scene"),
    match("scene", 2, "abcd"),
    match("scene", 1, "abc"),
  ],
});
check(
  "authoritative scene rank wins over local exact and fuzzy scores",
  flattenOmniboxSections(searchOmniboxItems(rankItems, "abc")).map((item) => item.kind === "scene" ? item.sceneId : 0).join(",") === "5,4,3,2,1",
);
const reversedRank = [...rankItems].reverse();
check(
  "authoritative rank is independent of the item array order",
  flattenOmniboxSections(searchOmniboxItems(rankItems, "abc")).map((item) => item.key).join(",")
    === flattenOmniboxSections(searchOmniboxItems(reversedRank, "abc")).map((item) => item.key).join(","),
);
const unicodeServerItems = buildOmniboxItems({
  commands: [], panels: [], projects: [], recentProjectIds: [],
  projectMatches: [match("scene", 6, "Straße")],
});
check(
  "authoritative server matches survive narrower client Unicode folding",
  flattenOmniboxSections(searchOmniboxItems(unicodeServerItems, "STRASSE"))[0]?.key === "scene:6",
);
const psykeRankItems = buildOmniboxItems({
  commands: [], panels: [], projects: [], recentProjectIds: [],
  projectMatches: [
    match("psyke", 8, "Zulu", "needle"),
    match("scene", 6, "Interleaved scene", "needle"),
    match("psyke", 7, "Alpha", "needle"),
  ],
});
check(
  "authoritative PSYKE rank survives interleaved server result kinds",
  flattenOmniboxSections(searchOmniboxItems(psykeRankItems, "needle"))
    .filter((item) => item.kind === "psyke")
    .map((item) => item.kind === "psyke" ? item.psykeEntryId : 0)
    .join(",") === "8,7",
);
const localRankItems = buildOmniboxItems({
  commands: createCommandRegistry([
    { id: "local-substring", category: "View", label: "xabc", run: () => undefined },
    { id: "local-exact", category: "View", label: "abc", run: () => undefined },
    { id: "local-prefix", category: "View", label: "abcd", run: () => undefined },
  ]).list(),
  panels: [], projects: [], recentProjectIds: [], projectMatches: [],
});
check(
  "local command ranking remains exact then prefix then substring",
  flattenOmniboxSections(searchOmniboxItems(localRankItems, "abc")).map((item) => item.key).join(",")
    === "command:local-exact,command:local-prefix,command:local-substring",
);
const capped = searchOmniboxItems(items, "alpha", { perGroupLimit: 1, totalLimit: 3 });
check("per-group result cap is enforced", capped.every((section) => section.items.length === 1));
check("overall result cap is enforced", flattenOmniboxSections(capped).length === 3);

const disabledFirst = items.filter((item) => item.kind === "command");
check("first enabled index skips disabled options", firstEnabledOmniboxIndex([...disabledFirst].reverse()) === 1);
check("forward keyboard selection skips disabled options", moveOmniboxSelection([...disabledFirst].reverse(), -1, 1) === 1);
check("backward keyboard selection wraps", moveOmniboxSelection(disabledFirst, 0, -1) === 0);
check("all-disabled selection returns -1", moveOmniboxSelection([{ disabled: true }], 0, 1) === -1);
check("stable DOM id does not depend on array position", omniboxOptionDomId("box", "scene:10") === omniboxOptionDomId("box", "scene:10"));
check("different item keys produce different DOM ids", omniboxOptionDomId("box", "scene:10") !== omniboxOptionDomId("box", "scene:11"));

check("recent parsing rejects malformed JSON", parseRecentProjectIds("not-json").length === 0);
check("recent parsing deduplicates and validates ids", parseRecentProjectIds("[2,2,-1,3.5,1]").join(",") === "2,1");
check("recent promotion moves the project to the front", rememberRecentProject([3, 2, 1], 2).join(",") === "2,3,1");
check("recent promotion obeys its cap", rememberRecentProject([4, 3, 2, 1], 5, 3).join(",") === "5,4,3");

const activationOrder: string[] = [];
const activationRegistry = createCommandRegistry([{
  id: "run",
  kind: "Command",
  label: "Run",
  run: () => { activationOrder.push("command"); },
}]);
const activationContext = {
  flush: async () => { activationOrder.push("flush"); },
  registry: activationRegistry,
  navigate: async (panel: string, options?: { sceneId?: number; noteId?: number; psykeEntryId?: number; commentId?: number }) => {
    activationOrder.push(`navigate:${panel}:${options?.sceneId ?? options?.noteId ?? options?.psykeEntryId ?? options?.commentId ?? ""}`);
    return true;
  },
  selectProject: async (projectId: number) => { activationOrder.push(`project:${projectId}`); return true; },
};
const activationItems: OmniboxItem[] = [
  { key: "command:run", kind: "command", group: "Commands", commandId: "run", label: "Run", detail: "Command", keywords: [], disabled: false, showWhenEmpty: true, priority: 0 },
  { key: "panel:outline", kind: "panel", group: "Panels", panelId: "outline", label: "Outline", detail: "Panel", keywords: [], disabled: false, showWhenEmpty: true, priority: 0 },
  { key: "scene:7", kind: "scene", group: "Scenes", sceneId: 7, label: "Seven", detail: "Scene", keywords: [], disabled: false, showWhenEmpty: false, priority: 0 },
  { key: "note:30", kind: "note", group: "Notes", noteId: 30, label: "Thirty", detail: "Note", keywords: [], disabled: false, showWhenEmpty: false, priority: 0 },
  { key: "psyke:8", kind: "psyke", group: "PSYKE", psykeEntryId: 8, label: "Eight", detail: "PSYKE", keywords: [], disabled: false, showWhenEmpty: false, priority: 0 },
  { key: "comment:40", kind: "comment", group: "Comments", commentId: 40, label: "Forty", detail: "Comment", keywords: [], disabled: false, showWhenEmpty: false, priority: 0 },
  { key: "project:9", kind: "project", group: "Projects", projectId: 9, label: "Nine", detail: "Project", keywords: [], disabled: false, showWhenEmpty: true, priority: 0 },
];
for (const item of activationItems) await activateOmniboxItem(item, activationContext);
check("every activation drains saves first", activationOrder.filter((value) => value === "flush").length === activationItems.length);
check("command dispatch uses registry", activationOrder.includes("command"));
check("panel dispatch uses its panel id", activationOrder.includes("navigate:outline:"));
check("scene dispatch targets manuscript", activationOrder.includes("navigate:manuscript:7"));
check("note dispatch targets the exact Notes editor", activationOrder.includes("navigate:notes:30"));
check("PSYKE dispatch targets the bible", activationOrder.includes("navigate:psyke:8"));
check("comment dispatch targets the exact Comments thread", activationOrder.includes("navigate:comments:40"));
check("project dispatch uses host handoff", activationOrder.includes("project:9"));

let unsafeNavigation = 0;
try {
  await activateOmniboxItem(activationItems[5]!, {
    ...activationContext,
    flush: async () => { throw new Error("unsaved"); },
    navigate: async () => { unsafeNavigation += 1; return true; },
  });
} catch { /* expected */ }
check("failed save barrier prevents comment navigation", unsafeNavigation === 0);
check("false host handoff remains a failed activation", !(await activateOmniboxItem(activationItems[6]!, { ...activationContext, selectProject: async () => false })));
check("disabled activation is inert", !(await activateOmniboxItem({ ...activationItems[0]!, disabled: true }, activationContext)));

const commandPlan: PsykeConsoleCommandPlanDTO = {
  plan_id: "plan-1",
  command: "open",
  normalized_command: "/open scene 7",
  action: "open_scene",
  summary: "Open scene seven",
  effects: ["Open the scene"],
  requires_confirmation: false,
  mutates: false,
  target_type: "scene",
  target_id: 7,
  expires_at: new Date(Date.now() + 10_000).toISOString(),
};
let identity = { projectId: 4 as number | undefined, sceneId: 3 as number | null };
const planOrder: string[] = [];
const planResult = await executeOmniboxPlan({
  plan: commandPlan,
  owner: { projectId: 4, sceneId: 3, planId: "plan-1" },
  getIdentity: () => identity,
  flush: async () => { planOrder.push("flush"); },
  execute: async () => {
    planOrder.push("execute");
    return { ok: true, action: "open_scene", message: "Opened", mutated: false, target_type: "scene", target_id: 7 };
  },
});
check("plan execution drains before calling the core", planOrder.join(",") === "flush,execute");
check("plan execution returns authoritative target", planResult.target_id === 7);

let staleWrites = 0;
try {
  await executeOmniboxPlan({
    plan: commandPlan,
    owner: { projectId: 99, sceneId: 3, planId: "plan-1" },
    getIdentity: () => identity,
    flush: async () => undefined,
    execute: async () => { staleWrites += 1; throw new Error("must not run"); },
  });
} catch (error) {
  check("stale plan is rejected before flushing", error instanceof StaleOmniboxPlanError);
}
check("stale plan performs no write", staleWrites === 0);

identity = { projectId: 4, sceneId: 3 };
try {
  await executeOmniboxPlan({
    plan: commandPlan,
    owner: { projectId: 4, sceneId: 3, planId: "plan-1" },
    getIdentity: () => identity,
    flush: async () => { identity = { projectId: 5, sceneId: 3 }; },
    execute: async () => { staleWrites += 1; throw new Error("must not run"); },
  });
} catch (error) {
  check("identity is revalidated after save barrier", error instanceof StaleOmniboxPlanError);
}
check("handoff during flush performs no command write", staleWrites === 0);

console.log(`Omnibox model/runtime tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} omnibox test(s) failed`);
