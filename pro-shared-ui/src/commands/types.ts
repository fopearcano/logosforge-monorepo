/** A command may use the existing palette `kind` name or the broader category name. */
export type CommandClassification =
  | { readonly category: string; readonly kind?: string }
  | { readonly kind: string; readonly category?: string };

/** Runtime-only Studio command. API command DTOs continue to belong in ui-contracts. */
export type CommandDescriptor = CommandClassification & {
  readonly id: string;
  readonly label: string;
  readonly keywords?: readonly string[];
  readonly aliases?: readonly string[];
  readonly shortcut?: string;
  /** False keeps a native/menu-only command out of the unified Studio omnibox. */
  readonly showInOmnibox?: boolean;
  readonly enabled?: boolean | (() => boolean);
  readonly run: () => unknown | Promise<unknown>;
};

export interface CommandRegistry {
  /** Commands in registration order. The returned array is a defensive copy. */
  list(): readonly CommandDescriptor[];
  /** Resolve a stable id first, then an alias. Matching is trimmed and case-insensitive. */
  resolve(idOrAlias: string): CommandDescriptor | undefined;
  /** Rank matching commands deterministically; an empty query preserves registration order. */
  search(query: string): readonly CommandDescriptor[];
  /** Resolve, check availability, and await the command handler. */
  execute(idOrAlias: string): Promise<unknown>;
}

export function commandCategory(command: CommandDescriptor): string {
  return command.category ?? command.kind ?? "Command";
}

export function isCommandEnabled(command: CommandDescriptor): boolean {
  return typeof command.enabled === "function"
    ? command.enabled()
    : command.enabled !== false;
}
