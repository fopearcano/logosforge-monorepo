import type { InlineCommentDTO, SceneDTO } from "@logosforge/ui-contracts";

const SECOND = 1_000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

const relativeFormatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function formatRelativeTime(value: string, now = Date.now()): string {
  const timestamp = new Date(value).getTime();
  if (!value || !Number.isFinite(timestamp)) return "Unknown time";
  const delta = timestamp - now;
  const absolute = Math.abs(delta);
  const [divisor, unit]: [number, Intl.RelativeTimeFormatUnit] = absolute >= YEAR
    ? [YEAR, "year"]
    : absolute >= MONTH
      ? [MONTH, "month"]
      : absolute >= WEEK
        ? [WEEK, "week"]
        : absolute >= DAY
          ? [DAY, "day"]
          : absolute >= HOUR
            ? [HOUR, "hour"]
            : absolute >= MINUTE
              ? [MINUTE, "minute"]
              : [SECOND, "second"];
  return relativeFormatter.format(Math.round(delta / divisor), unit);
}

export function absoluteTime(value: string): string {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleString() : "Unknown time";
}

export function isImportedSource(sourceId: string): boolean {
  return sourceId.trim().length > 0;
}

export function sceneName(sceneId: number, scenesById: ReadonlyMap<number, SceneDTO>): string {
  const scene = scenesById.get(sceneId);
  return scene?.title?.trim() || `Scene #${sceneId}`;
}

export function anchorLabel(comment: InlineCommentDTO, scenesById: ReadonlyMap<number, SceneDTO>): string {
  const { anchor } = comment;
  const start = `${sceneName(anchor.start_scene_id, scenesById)} · ${anchor.start_field} ${anchor.from_offset}`;
  const end = `${sceneName(anchor.end_scene_id, scenesById)} · ${anchor.end_field} ${anchor.to_offset}`;
  if (anchor.start_scene_id === anchor.end_scene_id && anchor.start_field === anchor.end_field) {
    return `${sceneName(anchor.start_scene_id, scenesById)} · ${anchor.start_field} ${anchor.from_offset}–${anchor.to_offset}`;
  }
  return `${start} → ${end}`;
}

function markdownBlockquote(value: string): string {
  const normalized = value.replace(/\r\n?/g, "\n");
  return normalized.split("\n").map((line) => `> ${line}`).join("\n");
}

function markdownBody(value: string): string {
  return value.trim() || "_(Empty comment)_";
}

export function buildCommentReport(
  comments: readonly InlineCommentDTO[],
  scenesById: ReadonlyMap<number, SceneDTO>,
  generatedAt = new Date(),
): string {
  const lines = [
    "# LogosForge comment report",
    "",
    `Generated: ${generatedAt.toISOString()}`,
    `Threads: ${comments.length} (${comments.filter((comment) => !comment.resolved).length} open, ${comments.filter((comment) => comment.resolved).length} resolved)`,
    "",
  ];
  if (comments.length === 0) {
    lines.push("_No comment threads._", "");
    return lines.join("\n");
  }
  comments.forEach((comment, index) => {
    lines.push(
      `## ${index + 1}. ${comment.resolved ? "Resolved" : "Open"} — ${sceneName(comment.anchor.start_scene_id, scenesById)}`,
      "",
      `- Anchor: ${anchorLabel(comment, scenesById)}`,
      `- Created: ${comment.created_at}`,
      `- Updated: ${comment.updated_at}`,
      `- Provenance: ${isImportedSource(comment.source_id) ? `Imported (${comment.source_id})` : "Native Pro"}`,
      "",
      "### Quoted text",
      "",
      markdownBlockquote(comment.quote || "(No quoted text)"),
      "",
      "### Comment",
      "",
      markdownBody(comment.body),
      "",
      `### Replies (${comment.replies.length})`,
      "",
    );
    if (comment.replies.length === 0) {
      lines.push("_No replies._", "");
    } else {
      [...comment.replies]
        .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
        .forEach((reply) => {
          const provenance = isImportedSource(reply.source_id) ? ` · imported (${reply.source_id})` : "";
          lines.push(`**${reply.author || "Unknown author"}** · ${reply.created_at}${provenance}`, "", markdownBody(reply.body), "");
        });
    }
    lines.push("---", "");
  });
  return lines.join("\n");
}

export function commentReportFilename(projectId: number | undefined): string {
  return `logosforge-comments${projectId == null ? "" : `-${projectId}`}.md`;
}
