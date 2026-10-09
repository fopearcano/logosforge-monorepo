/**
 * Canonical, platform-neutral keyboard shortcuts for every Pro workspace
 * surface. `Primary` renders as Command on macOS and Control elsewhere.
 *
 * The larger catalog deliberately lives in one reserved modifier family so
 * panel navigation never consumes ordinary typing. Familiar pre-existing
 * shortcuts remain unchanged.
 */
export interface StudioPanelShortcutDefinition {
  readonly id: string;
  readonly label: string;
  readonly group: "CORE" | "PLAN" | "STRUCTURE" | "ANALYTICS" | "BIBLE" | "SYSTEM" | "AI";
  readonly shortcut: string;
}

export const STUDIO_PANEL_SHORTCUTS: readonly StudioPanelShortcutDefinition[] = [
  { id: "projects", label: "Projects", group: "CORE", shortcut: "Primary+O" },
  { id: "dashboard", label: "Dashboard", group: "CORE", shortcut: "Primary+2" },
  { id: "manuscript", label: "Manuscript", group: "CORE", shortcut: "Primary+1" },
  { id: "notes", label: "Notes", group: "CORE", shortcut: "Primary+Alt+Shift+N" },
  { id: "comments", label: "Comments", group: "CORE", shortcut: "Primary+Shift+C" },
  { id: "dexters-room", label: "Dexter's Room", group: "CORE", shortcut: "Primary+Alt+Shift+V" },

  { id: "outline", label: "Outline", group: "PLAN", shortcut: "Primary+3" },
  { id: "story-grid", label: "Story Grid", group: "PLAN", shortcut: "Primary+Alt+Shift+G" },
  { id: "timeline", label: "Timeline", group: "PLAN", shortcut: "Primary+4" },
  { id: "canvas-plot", label: "Canvas Plot", group: "PLAN", shortcut: "Primary+Alt+Shift+X" },
  { id: "series", label: "Series", group: "PLAN", shortcut: "Primary+Alt+Shift+S" },

  { id: "structure", label: "Structure", group: "STRUCTURE", shortcut: "Primary+Alt+Shift+U" },
  { id: "acts", label: "Acts", group: "STRUCTURE", shortcut: "Primary+Alt+Shift+A" },
  { id: "beats", label: "Beats", group: "STRUCTURE", shortcut: "Primary+Alt+Shift+B" },
  { id: "chapters", label: "Chapters", group: "STRUCTURE", shortcut: "Primary+Alt+Shift+H" },
  { id: "structure-analysis", label: "Structure Analysis", group: "STRUCTURE", shortcut: "Primary+Alt+Shift+R" },
  { id: "format-studio", label: "Format Studio", group: "STRUCTURE", shortcut: "Primary+Alt+Shift+F" },

  { id: "health", label: "Health", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+L" },
  { id: "pacing", label: "Pacing", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+I" },
  { id: "balance", label: "Balance", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+E" },
  { id: "tags", label: "Tags", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+T" },
  { id: "continuity", label: "Continuity", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+Q" },
  { id: "decision-radar", label: "Decision Radar", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+W" },
  { id: "guided-workflows", label: "Guided Workflows", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+5" },
  { id: "adapt", label: "Adapt", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+6" },
  { id: "review", label: "Review", group: "ANALYTICS", shortcut: "Primary+Alt+Shift+7" },

  { id: "psyke", label: "PSYKE", group: "BIBLE", shortcut: "Primary+Alt+Shift+Y" },
  { id: "progressions", label: "Progressions", group: "BIBLE", shortcut: "Primary+Alt+Shift+P" },
  { id: "characters", label: "Characters", group: "BIBLE", shortcut: "Primary+Alt+Shift+K" },
  { id: "theme-scenes", label: "Theme Scenes", group: "BIBLE", shortcut: "Primary+Alt+Shift+8" },
  { id: "graph", label: "Graph", group: "BIBLE", shortcut: "Primary+Alt+Shift+9" },

  { id: "plugins", label: "Plugins", group: "SYSTEM", shortcut: "Primary+Alt+Shift+0" },
  { id: "connector", label: "Connector", group: "SYSTEM", shortcut: "Primary+Alt+Shift+C" },
  { id: "export", label: "Export", group: "SYSTEM", shortcut: "Primary+E" },
  { id: "ai-settings", label: "AI Settings", group: "SYSTEM", shortcut: "Primary+Alt+Shift+Z" },
  { id: "settings", label: "Settings", group: "SYSTEM", shortcut: "Primary+Comma" },
  { id: "help", label: "Help", group: "SYSTEM", shortcut: "Primary+Alt+Shift+D" },

  { id: "ai-companions", label: "AI Companions", group: "AI", shortcut: "Primary+J" },
];

const SHORTCUT_BY_PANEL_ID = new Map(
  STUDIO_PANEL_SHORTCUTS.map((definition) => [definition.id, definition.shortcut]),
);

export function studioPanelShortcut(panelId: string): string | undefined {
  return SHORTCUT_BY_PANEL_ID.get(panelId);
}

export interface KeyboardShortcutEventLike {
  readonly key: string;
  readonly code?: string;
  readonly ctrlKey: boolean;
  readonly metaKey: boolean;
  readonly altKey: boolean;
  readonly shiftKey: boolean;
  readonly repeat?: boolean;
  readonly defaultPrevented?: boolean;
  readonly isComposing?: boolean;
  getModifierState?(key: string): boolean;
}

function shortcutKeyMatches(event: KeyboardShortcutEventLike, token: string): boolean {
  const expected = token.toLowerCase();
  if (expected === "comma") return event.key === "," || event.code === "Comma";
  if (/^[0-9]$/.test(expected)) {
    return event.key === expected || event.code === `Digit${expected}` || event.code === `Numpad${expected}`;
  }
  if (/^[a-z]$/.test(expected)) {
    return event.key.toLowerCase() === expected || event.code === `Key${expected.toUpperCase()}`;
  }
  return event.key.toLowerCase() === expected;
}

/** Match one canonical shortcut exactly, while never treating AltGr as a command. */
export function matchesKeyboardShortcut(
  event: KeyboardShortcutEventLike,
  shortcut: string,
): boolean {
  if (
    event.defaultPrevented
    || event.repeat
    || event.isComposing
    || event.getModifierState?.("AltGraph")
  ) return false;
  const tokens = shortcut.split("+").map((token) => token.trim()).filter(Boolean);
  const key = tokens.at(-1);
  if (!key) return false;
  const expectsPrimary = tokens.includes("Primary");
  const expectsAlt = tokens.includes("Alt");
  const expectsShift = tokens.includes("Shift");
  if ((event.ctrlKey || event.metaKey) !== expectsPrimary) return false;
  if (event.altKey !== expectsAlt || event.shiftKey !== expectsShift) return false;
  return shortcutKeyMatches(event, key);
}

export function panelIdForKeyboardShortcut(event: KeyboardShortcutEventLike): string | null {
  return STUDIO_PANEL_SHORTCUTS.find((definition) => (
    matchesKeyboardShortcut(event, definition.shortcut)
  ))?.id ?? null;
}

/** Human-readable key labels for docs and in-app guidance. */
export function formatStudioShortcut(shortcut: string, platform?: "mac" | "other"): string {
  const mac = platform ?? (
    typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)
      ? "mac"
      : "other"
  );
  return shortcut
    .replace("Primary", mac === "mac" ? "⌘" : "Ctrl")
    .replace("Alt", mac === "mac" ? "⌥" : "Alt")
    .replace("Shift", mac === "mac" ? "⇧" : "Shift")
    .replace("Comma", ",")
    .replaceAll("+", mac === "mac" ? "" : "+");
}
