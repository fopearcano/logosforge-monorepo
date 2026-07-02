/**
 * Billy's model appends a machine directive after its prose, e.g.
 *   <action>{"action":"create_scene","args":{…},"label":"Establishing Ambient Sounds"}</action>
 * The tag is often UNCLOSED / truncated (no </action>) or carries a stray trailing
 * brace. We lift it out of the visible transcript and turn it into a clickable
 * suggestion card (see BillyMessageList) instead of leaking raw JSON to the writer.
 */

export interface BillyAction {
  /** Human-readable suggestion: label > prettified action verb. */
  label: string;
  /** The machine verb (may be empty), e.g. "create_scene". */
  action: string;
  /** The raw payload — used as the card's hover title. */
  raw: string;
}

export interface ParsedBillyMessage {
  /** Prose with every <action> block removed. */
  text: string;
  /** Parsed suggestion directives, in order of appearance. */
  actions: BillyAction[];
}

/** Split an assistant message into visible prose + parsed <action> suggestions. */
export function parseBillyMessage(content: string): ParsedBillyMessage {
  const actions: BillyAction[] = [];
  const open = /<action\b[^>]*>/gi;
  let m: RegExpExecArray | null;
  while ((m = open.exec(content))) {
    const rest = content.slice(m.index + m[0].length);
    const close = rest.search(/<\/action>/i);
    const payload = (close >= 0 ? rest.slice(0, close) : rest).trim();
    const parsed = parseActionPayload(payload);
    if (parsed) actions.push(parsed);
  }
  return { text: stripActionBlocks(content), actions };
}

/** The visible prose only — <action> directives (complete or truncated) removed. */
export function stripActionBlocks(text: string): string {
  return text
    .replace(/<action\b[^>]*>[\s\S]*?<\/action>/gi, '') // complete directive(s)
    .replace(/<action\b[^>]*>[\s\S]*$/i, '') // truncated / unclosed trailing directive
    .replace(/\n{3,}/g, '\n\n') // tidy the gap it leaves behind
    .trimEnd();
}

function parseActionPayload(payload: string): BillyAction | null {
  const raw = payload.trim();
  let obj: Record<string, unknown> | null = null;
  const start = raw.indexOf('{');
  if (start >= 0) {
    // The model sometimes trails a stray brace ("…}}") or truncates; try each '}'
    // close from longest to shortest until one parses cleanly.
    for (let end = raw.length; end > start; end -= 1) {
      if (raw[end - 1] !== '}') continue;
      try {
        obj = JSON.parse(raw.slice(start, end));
        break;
      } catch {
        /* keep trying a shorter slice */
      }
    }
  }
  let label = '';
  let action = '';
  if (obj) {
    if (typeof obj.label === 'string') label = obj.label;
    if (typeof obj.action === 'string') action = obj.action;
  } else {
    // Unparseable JSON — salvage the fields we care about by regex.
    label = (raw.match(/"label"\s*:\s*"([^"]+)"/i) || [])[1] ?? '';
    action = (raw.match(/"action"\s*:\s*"([^"]+)"/i) || [])[1] ?? '';
  }
  label = label.trim() || prettify(action);
  if (!label) return null;
  return { label, action: action.trim(), raw };
}

function prettify(action: string): string {
  return action
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
