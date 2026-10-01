import {
  CommandDisabledError,
  CommandNotFoundError,
  DuplicateCommandIdError,
  createCommandRegistry,
  isCommandEnabled,
  searchCommands,
  type CommandDescriptor,
} from "../src/commands";

let passed = 0;
const failures: string[] = [];

function check(label: string, condition: boolean): void {
  if (condition) passed += 1;
  else failures.push(label);
}

async function rejectsWith(label: string, work: () => unknown, expected: new (...args: never[]) => Error): Promise<void> {
  try {
    await work();
    failures.push(label);
  } catch (error) {
    check(label, error instanceof expected);
  }
}

const calls: string[] = [];
const commands: CommandDescriptor[] = [
  {
    id: "workspace.open-manuscript",
    kind: "Go",
    label: "Manuscript",
    aliases: ["write"],
    keywords: ["editor", "draft"],
    shortcut: "Primary+1",
    run: () => { calls.push("manuscript"); return "opened"; },
  },
  {
    id: "ai.open-billy",
    category: "AI",
    label: "Billy — Project Assistant",
    aliases: ["assistant"],
    keywords: ["chat", "project"],
    run: async () => { calls.push("billy"); return 42; },
  },
  {
    id: "workspace.focus",
    kind: "View",
    label: "Enter focus mode",
    enabled: () => true,
    run: () => { calls.push("focus"); },
  },
  {
    id: "workspace.disabled",
    kind: "View",
    label: "Unavailable command",
    enabled: false,
    run: () => { calls.push("disabled"); },
  },
];

const registry = createCommandRegistry(commands);
const listed = registry.list();
check("list preserves registration order", listed.map((command) => command.id).join(",") === commands.map((command) => command.id).join(","));
(listed as CommandDescriptor[]).pop();
check("list returns a defensive copy", registry.list().length === commands.length);
check("resolve finds an id case-insensitively", registry.resolve(" WORKSPACE.OPEN-MANUSCRIPT ") === commands[0]);
check("resolve finds an alias case-insensitively", registry.resolve("Assistant") === commands[1]);
check("resolve returns undefined for an unknown command", registry.resolve("missing") === undefined);

check("empty search preserves registration order", registry.search("").map((command) => command.id).join(",") === commands.map((command) => command.id).join(","));
check("exact alias search ranks its command first", registry.search("assistant")[0]?.id === "ai.open-billy");
check("keyword search finds commands", registry.search("draft")[0]?.id === "workspace.open-manuscript");
check("category search finds commands", registry.search("ai")[0]?.id === "ai.open-billy");
check("subsequence search is supported", registry.search("mnscrpt")[0]?.id === "workspace.open-manuscript");
check("non-matching commands are omitted", registry.search("zzzzzz").length === 0);

const tied: CommandDescriptor[] = [
  { id: "z", kind: "Go", label: "Beta", keywords: ["same"], run: () => undefined },
  { id: "a", kind: "Go", label: "Alpha", keywords: ["same"], run: () => undefined },
];
check("score ties use stable label then id ordering", searchCommands(tied, "same").map((command) => command.id).join(",") === "a,z");

check("enabled defaults to true", isCommandEnabled(commands[0]!));
check("enabled accepts a predicate", isCommandEnabled(commands[2]!));
check("enabled false is honored", !isCommandEnabled(commands[3]!));
check("execute awaits sync handlers", await registry.execute("write") === "opened" && calls.at(-1) === "manuscript");
check("execute awaits async handlers", await registry.execute("ai.open-billy") === 42 && calls.at(-1) === "billy");
await rejectsWith("execute rejects unknown commands", () => registry.execute("missing"), CommandNotFoundError);
await rejectsWith("execute rejects disabled commands", () => registry.execute("workspace.disabled"), CommandDisabledError);
check("disabled handler was not called", !calls.includes("disabled"));

await rejectsWith(
  "duplicate ids are rejected case-insensitively",
  () => createCommandRegistry([
    { id: "Duplicate", kind: "Test", label: "One", run: () => undefined },
    { id: " duplicate ", kind: "Test", label: "Two", run: () => undefined },
  ]),
  DuplicateCommandIdError,
);

console.log(`Command registry tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} command registry test(s) failed`);
