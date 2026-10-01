import { commandCategory, type CommandDescriptor } from "./types";

interface SearchField {
  value: string;
  weight: number;
}

interface RankedCommand {
  command: CommandDescriptor;
  score: number;
  labelKey: string;
  idKey: string;
  registrationIndex: number;
}

export function normalizeCommandText(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function commandFields(command: CommandDescriptor): SearchField[] {
  const fields: SearchField[] = [
    { value: command.label, weight: 80 },
    { value: command.id, weight: 70 },
    { value: commandCategory(command), weight: 20 },
  ];
  for (const alias of command.aliases ?? []) fields.push({ value: alias, weight: 75 });
  for (const keyword of command.keywords ?? []) fields.push({ value: keyword, weight: 45 });
  if (command.shortcut) fields.push({ value: command.shortcut, weight: 10 });
  return fields;
}

function subsequenceScore(needle: string, haystack: string): number | null {
  let needleIndex = 0;
  let firstMatch = -1;
  let lastMatch = -1;
  for (let index = 0; index < haystack.length && needleIndex < needle.length; index += 1) {
    if (haystack[index] !== needle[needleIndex]) continue;
    if (firstMatch < 0) firstMatch = index;
    lastMatch = index;
    needleIndex += 1;
  }
  if (needleIndex !== needle.length) return null;
  const span = lastMatch - firstMatch + 1;
  const gaps = span - needle.length;
  return Math.max(1, 1_000 - gaps * 8 - firstMatch * 2);
}

function fieldScore(query: string, field: SearchField): number | null {
  const value = normalizeCommandText(field.value);
  if (!value) return null;
  if (value === query) return 5_000 + field.weight;
  if (value.startsWith(query)) return 4_000 + field.weight - Math.min(200, value.length - query.length);

  const wordIndex = value.split(/[^a-z0-9]+/).findIndex((word) => word.startsWith(query));
  if (wordIndex >= 0) return 3_000 + field.weight - wordIndex;

  const substringIndex = value.indexOf(query);
  if (substringIndex >= 0) return 2_000 + field.weight - Math.min(500, substringIndex);

  const fuzzy = subsequenceScore(query.replace(/\s/g, ""), value.replace(/\s/g, ""));
  return fuzzy == null ? null : fuzzy + field.weight;
}

function scoreCommand(command: CommandDescriptor, query: string): number | null {
  const fields = commandFields(command);
  let best = -1;
  for (const field of fields) {
    const score = fieldScore(query, field);
    if (score != null) best = Math.max(best, score);
  }
  if (best >= 0) return best;

  const terms = query.split(" ").filter(Boolean);
  if (terms.length < 2) return null;
  let total = 0;
  for (const term of terms) {
    let termBest = -1;
    for (const field of fields) {
      const score = fieldScore(term, field);
      if (score != null) termBest = Math.max(termBest, score);
    }
    if (termBest < 0) return null;
    total += termBest;
  }
  return Math.round(total / terms.length);
}

function compareText(left: string, right: string): number {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

/**
 * Small, dependency-free command matcher. Exact/prefix/word/substring matches
 * outrank subsequences; stable text keys break score ties across runtimes.
 */
export function searchCommands(
  commands: readonly CommandDescriptor[],
  query: string,
): readonly CommandDescriptor[] {
  const normalizedQuery = normalizeCommandText(query);
  if (!normalizedQuery) return [...commands];

  const ranked: RankedCommand[] = [];
  commands.forEach((command, registrationIndex) => {
    const score = scoreCommand(command, normalizedQuery);
    if (score == null) return;
    ranked.push({
      command,
      score,
      labelKey: normalizeCommandText(command.label),
      idKey: normalizeCommandText(command.id),
      registrationIndex,
    });
  });

  ranked.sort((left, right) => (
    right.score - left.score
    || compareText(left.labelKey, right.labelKey)
    || compareText(left.idKey, right.idKey)
    || left.registrationIndex - right.registrationIndex
  ));
  return ranked.map(({ command }) => command);
}
