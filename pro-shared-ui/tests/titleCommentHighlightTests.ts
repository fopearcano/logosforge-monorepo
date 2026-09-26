import {
  buildTitleCommentOverlayTokens,
  titleCommentIdsAtOffset,
  type TitleCommentHighlight,
} from "../src/components/manuscript/titleCommentHighlights";

let passed = 0;
function check(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  passed += 1;
}

const highlight = (
  commentId: number,
  fromOffset: number,
  toOffset: number,
  resolved = false,
): TitleCommentHighlight => ({ commentId, fromOffset, toOffset, resolved });

const title = "Signal 🚀 Return";
const emojiTokens = buildTitleCommentOverlayTokens(title, [highlight(7, 7, 9)]);
check(emojiTokens.map((token) => token.text).join("") === title, "tokens preserve the complete title");
check(emojiTokens.filter((token) => token.commentIds.length).length === 1, "one exact highlighted run is produced");
check(emojiTokens.find((token) => token.commentIds.length)?.text === "🚀", "UTF-16 offsets retain the complete emoji");
check(emojiTokens.find((token) => token.commentIds.length)?.fromOffset === 7, "highlight starts at the browser input offset");
check(emojiTokens.find((token) => token.commentIds.length)?.toOffset === 9, "highlight ends at the browser input offset");

const overlapTokens = buildTitleCommentOverlayTokens("ABCDE", [
  highlight(12, 1, 4, true),
  highlight(3, 2, 5, false),
]);
const overlap = overlapTokens.find((token) => token.text === "CD");
check(overlap?.commentIds.join(",") === "3,12", "overlapping marks aggregate sorted comment ids");
check(overlap?.resolved === false, "an overlap stays open when any thread is open");
check(overlapTokens.find((token) => token.text === "B")?.resolved === true, "a resolved-only run uses resolved presentation");
check(overlapTokens.map((token) => token.text).join("") === "ABCDE", "overlap segmentation never duplicates title text");

const pointTokens = buildTitleCommentOverlayTokens("Draft", [
  highlight(9, 2, 2),
  highlight(4, 2, 2, true),
]);
const point = pointTokens.find((token) => token.kind === "point");
check(point?.fromOffset === 2 && point.toOffset === 2, "zero-width legacy anchors retain their exact position");
check(point?.commentIds.join(",") === "4,9", "coincident point anchors are aggregated deterministically");
check(point?.resolved === false, "coincident points remain open when any thread is open");
check(pointTokens.map((token) => token.text).join("") === "Draft", "point markers do not consume or shift title text");

const staleTokens = buildTitleCommentOverlayTokens("Short", [
  highlight(1, -20, 2),
  highlight(2, 3, 200),
  highlight(3, 4, 1),
  { ...highlight(4, 0, 1), fromOffset: Number.NaN },
]);
check(staleTokens.map((token) => token.text).join("") === "Short", "stale ranges still cover the title once");
check(staleTokens.find((token) => token.fromOffset === 0 && token.toOffset === 2)?.commentIds.join(",") === "1", "out-of-bounds starts are clamped safely");
check(staleTokens.find((token) => token.fromOffset === 3 && token.toOffset === 5)?.commentIds.join(",") === "2", "out-of-bounds ends are clamped safely");
check(!staleTokens.some((token) => token.commentIds.includes(3)), "reversed corrupt ranges are ignored");
check(!staleTokens.some((token) => token.commentIds.includes(4)), "non-finite corrupt ranges are ignored");

const duplicated = buildTitleCommentOverlayTokens("One", [
  highlight(5, 0, 3, true),
  highlight(5, 0, 3, false),
]);
check(duplicated[0]?.commentIds.join(",") === "5", "duplicate records do not duplicate data-comment ids");
check(duplicated[0]?.resolved === false, "duplicate state conservatively preserves an open thread");

const plain = buildTitleCommentOverlayTokens("Untouched", []);
check(plain.length === 1 && plain[0]?.text === "Untouched", "an unmarked title remains a single plain run");
check(plain[0]?.commentIds.length === 0 && plain[0]?.resolved === false, "plain runs have no comment state");

const clickable = [
  highlight(8, 1, 4),
  highlight(3, 2, 5),
  highlight(11, 5, 5),
  highlight(20, 5, 7),
];
check(titleCommentIdsAtOffset(clickable, 3).join(",") === "3,8", "caret inside overlapping title marks activates that exact stack");
check(titleCommentIdsAtOffset(clickable, 1).join(",") === "8", "caret on an isolated range edge keeps the mark reachable");
check(titleCommentIdsAtOffset(clickable, 5).join(",") === "11", "an exact point mark wins over merely touching range edges");
check(titleCommentIdsAtOffset(clickable, 6).join(",") === "20", "caret inside the following title mark activates only that mark");
check(titleCommentIdsAtOffset(clickable, Number.NaN).length === 0, "invalid caret offsets activate no marks");

console.log(`Title comment highlight tests: ${passed} passed, 0 failed`);
