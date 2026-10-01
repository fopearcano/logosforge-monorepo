import { searchCommands, normalizeCommandText } from "./search";
import {
  isCommandEnabled,
  type CommandDescriptor,
  type CommandRegistry,
} from "./types";

export class DuplicateCommandIdError extends Error {
  constructor(id: string) {
    super(`Duplicate command id: ${id}`);
    this.name = "DuplicateCommandIdError";
  }
}

export class CommandNotFoundError extends Error {
  constructor(idOrAlias: string) {
    super(`Unknown command: ${idOrAlias}`);
    this.name = "CommandNotFoundError";
  }
}

export class CommandDisabledError extends Error {
  constructor(id: string) {
    super(`Command is disabled: ${id}`);
    this.name = "CommandDisabledError";
  }
}

/** Create an immutable-view registry over the supplied runtime command handlers. */
export function createCommandRegistry(
  descriptors: readonly CommandDescriptor[],
): CommandRegistry {
  const commands = [...descriptors];
  const byId = new Map<string, CommandDescriptor>();
  const byAlias = new Map<string, CommandDescriptor>();

  for (const command of commands) {
    const id = normalizeCommandText(command.id);
    if (!id) throw new Error("Command ids cannot be empty.");
    if (byId.has(id)) throw new DuplicateCommandIdError(command.id);
    byId.set(id, command);
  }

  // IDs always win over aliases. Otherwise the first registered alias wins,
  // which keeps resolution deterministic without making descriptive aliases a
  // second global uniqueness domain.
  for (const command of commands) {
    for (const value of command.aliases ?? []) {
      const alias = normalizeCommandText(value);
      if (alias && !byId.has(alias) && !byAlias.has(alias)) byAlias.set(alias, command);
    }
  }

  const resolve = (idOrAlias: string): CommandDescriptor | undefined => {
    const key = normalizeCommandText(idOrAlias);
    return key ? byId.get(key) ?? byAlias.get(key) : undefined;
  };

  return Object.freeze({
    list: () => [...commands],
    resolve,
    search: (query: string) => searchCommands(commands, query),
    execute: async (idOrAlias: string) => {
      const command = resolve(idOrAlias);
      if (!command) throw new CommandNotFoundError(idOrAlias);
      if (!isCommandEnabled(command)) throw new CommandDisabledError(command.id);
      return await command.run();
    },
  });
}
