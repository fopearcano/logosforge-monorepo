/** Pure UTF-16 / TextQuote reconciliation tests (no React or DOM). */

import type {
  InlineCommentAnchorDTO,
  InlineCommentDTO,
  InlineCommentField,
  SceneDTO,
} from "@logosforge/ui-contracts";
import { Schema } from "@tiptap/pm/model";
import {
  commentSpans,
  createMultiFieldCommentDraft,
  createSingleFieldCommentDraft,
  findOrphanedCommentIds,
  isUtf16Boundary,
  locateComment,
  reconcileCommentSpans,
  reconciledCommentPatch,
} from "../src/components/manuscript/commentAnchors";
import {
  proseCommentDocumentRanges,
  proseDocumentPositionToTextOffset,
} from "../src/components/manuscript/ProseEditor";

let passed = 0;
const failures: string[] = [];

function check(label: string, condition: boolean): void {
  if (condition) passed += 1;
  else failures.push(label);
}

function equal(label: string, actual: unknown, expected: unknown): void {
  check(label, JSON.stringify(actual) === JSON.stringify(expected));
}

function scene(
  id: number,
  title: string,
  content: string,
  sortOrder = id,
): SceneDTO {
  return {
    id,
    title,
    content,
    sort_order: sortOrder,
    order_index: sortOrder,
    summary: "",
    synopsis: "",
    goal: "",
    conflict: "",
    outcome: "",
    beat: "",
    act: "",
    chapter: "",
    plotline: "",
    color_label: "",
    tags: [],
    character_ids: [],
    place_ids: [],
    who_knows_what: "",
  };
}

function anchor(
  startSceneId: number,
  startField: InlineCommentField,
  fromOffset: number,
  endSceneId: number,
  endField: InlineCommentField,
  toOffset: number,
  prefix = "",
  suffix = "",
): InlineCommentAnchorDTO {
  return {
    start_scene_id: startSceneId,
    start_field: startField,
    from_offset: fromOffset,
    end_scene_id: endSceneId,
    end_field: endField,
    to_offset: toOffset,
    prefix,
    suffix,
  };
}

function comment(
  id: number,
  value: InlineCommentAnchorDTO,
  quote: string,
  resolved = false,
): InlineCommentDTO {
  return {
    id,
    source_id: "",
    anchor: value,
    quote,
    body: "",
    resolved,
    replies: [],
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
    revision: id.toString(16).padStart(64, "0"),
  };
}

function fromDraft(id: number, draft: NonNullable<ReturnType<typeof createSingleFieldCommentDraft>>): InlineCommentDTO {
  return comment(id, draft.anchor, draft.quote);
}

function proseDoc(lines: string[]) {
  const schema = new Schema({
    nodes: {
      doc: { content: "paragraph+" },
      paragraph: { content: "text*" },
      text: { inline: true },
    },
  });
  return schema.node("doc", null, lines.map((line) => (
    schema.node("paragraph", null, line ? [schema.text(line)] : undefined)
  )));
}

// Native anchors capture exact text/context in JavaScript's UTF-16 units.
{
  const current = scene(1, "Chapter One", "The rain fell");
  const draft = createSingleFieldCommentDraft(current, "content", 4, 8);
  check("native draft exists", draft != null);
  equal("native quote", draft?.quote, "rain");
  equal("native anchor", draft?.anchor, anchor(1, "content", 4, 1, "content", 8, "The ", " fell"));
  check("collapsed native selection rejected", createSingleFieldCommentDraft(current, "content", 4, 4) == null);
  check("reversed native selection rejected", createSingleFieldCommentDraft(current, "content", 8, 4) == null);
  check("out-of-range native selection rejected", createSingleFieldCommentDraft(current, "content", 0, 99) == null);
}

// Astral characters consume two offsets and split-surrogate selections are never emitted.
{
  const current = scene(1, "Astral", "A😀B");
  check("UTF-16 boundary before astral", isUtf16Boundary(current.content, 1));
  check("UTF-16 split boundary detected", !isUtf16Boundary(current.content, 2));
  check("UTF-16 boundary after astral", isUtf16Boundary(current.content, 3));
  const draft = createSingleFieldCommentDraft(current, "content", 1, 3);
  equal("astral native quote", draft?.quote, "😀");
  equal("astral native offsets", [draft?.anchor.from_offset, draft?.anchor.to_offset], [1, 3]);
  check("astral end split rejected", createSingleFieldCommentDraft(current, "content", 1, 2) == null);
  check("astral start split rejected", createSingleFieldCommentDraft(current, "content", 2, 3) == null);

  const prefixBoundary = scene(2, "Astral context", `😀${"a".repeat(31)}X`);
  const prefixDraft = createSingleFieldCommentDraft(prefixBoundary, "content", 33, 34)!;
  check("prefix context never starts with a dangling low surrogate", prefixDraft.anchor.prefix.startsWith("😀"));
  const suffixBoundary = scene(3, "Astral context", `X${"a".repeat(31)}😀`);
  const suffixDraft = createSingleFieldCommentDraft(suffixBoundary, "content", 0, 1)!;
  check("suffix context never ends with a dangling high surrogate", suffixDraft.anchor.suffix.endsWith("😀"));
}

// Native ordered multi-field selections use stable scene/field endpoints and one
// newline separator for every traversed field.
{
  const scenes = [
    scene(1, "Chapter One", "The story starts here", 1),
    scene(2, "Chapter Two", "and it ends right there", 2),
  ];
  const acrossFields = createMultiFieldCommentDraft(
    scenes,
    { sceneId: 1, field: "title", offset: 8 },
    { sceneId: 1, field: "content", offset: 3 },
  );
  equal("multi-field native quote joins field slices", acrossFields?.quote, "One\nThe");
  equal(
    "multi-field native anchor keeps stable endpoints",
    acrossFields?.anchor,
    anchor(1, "title", 8, 1, "content", 3, "Chapter ", " story starts here"),
  );

  const acrossScenes = createMultiFieldCommentDraft(
    [...scenes].reverse(),
    { sceneId: 1, field: "content", offset: 4 },
    { sceneId: 2, field: "content", offset: 11 },
  );
  equal(
    "multi-scene draft follows canonical order and includes intermediate title",
    acrossScenes?.quote,
    "story starts here\nChapter Two\nand it ends",
  );
  equal(
    "multi-scene draft captures outer context",
    [acrossScenes?.anchor.prefix, acrossScenes?.anchor.suffix],
    ["The ", " right there"],
  );

  const astral = [scene(3, "Emoji", "A😀B", 3), scene(4, "Next", "C😀D", 4)];
  const astralDraft = createMultiFieldCommentDraft(
    astral,
    { sceneId: 3, field: "content", offset: 1 },
    { sceneId: 4, field: "content", offset: 3 },
  );
  check("multi-field draft preserves complete astral characters", astralDraft?.quote.startsWith("😀B") === true && astralDraft.quote.endsWith("C😀"));
  check(
    "multi-field draft rejects split-surrogate start",
    createMultiFieldCommentDraft(astral, { sceneId: 3, field: "content", offset: 2 }, { sceneId: 4, field: "content", offset: 3 }) == null,
  );
  check(
    "multi-field draft rejects split-surrogate end",
    createMultiFieldCommentDraft(astral, { sceneId: 3, field: "content", offset: 1 }, { sceneId: 4, field: "content", offset: 2 }) == null,
  );
  check(
    "multi-field draft rejects reversed document order",
    createMultiFieldCommentDraft(scenes, { sceneId: 2, field: "content", offset: 1 }, { sceneId: 1, field: "content", offset: 2 }) == null,
  );
  check(
    "multi-field draft rejects a missing endpoint",
    createMultiFieldCommentDraft(scenes, { sceneId: 999, field: "content", offset: 0 }, { sceneId: 2, field: "content", offset: 2 }) == null,
  );
  check(
    "multi-field same-scope collapsed selection is rejected",
    createMultiFieldCommentDraft(scenes, { sceneId: 1, field: "content", offset: 4 }, { sceneId: 1, field: "content", offset: 4 }) == null,
  );
  const emptyFields = [scene(5, "", "", 5), scene(6, "", "", 6)];
  check(
    "multi-field separator-only selection is rejected",
    createMultiFieldCommentDraft(emptyFields, { sceneId: 5, field: "content", offset: 0 }, { sceneId: 6, field: "title", offset: 0 }) == null,
  );
  equal(
    "multi-field helper shares same-field selection semantics",
    createMultiFieldCommentDraft(scenes, { sceneId: 1, field: "content", offset: 4 }, { sceneId: 1, field: "content", offset: 9 }),
    createSingleFieldCommentDraft(scenes[0]!, "content", 4, 9),
  );
}

// Stored position, ordinary insertion, and astral insertion relocation.
{
  const original = scene(1, "One", "The rain fell");
  const draft = createSingleFieldCommentDraft(original, "content", 4, 8)!;
  equal("stored span stays put", commentSpans(fromDraft(1, draft), [original]).map((s) => [s.sceneId, s.field, s.fromOffset, s.toOffset]), [[1, "content", 4, 8]]);

  const shifted = scene(1, "One", "Oh, The rain fell");
  equal("exact quote relocates after insertion", commentSpans(fromDraft(1, draft), [shifted]).map((s) => [s.fromOffset, s.toOffset]), [[8, 12]]);

  const astralShifted = scene(1, "One", "😀 Oh, The rain fell");
  const expected = astralShifted.content.indexOf("rain");
  equal("astral insertion counted as two UTF-16 units", commentSpans(fromDraft(1, draft), [astralShifted]).map((s) => [s.fromOffset, s.toOffset]), [[expected, expected + 4]]);
}

// Repeated quotes use context, then proximity, instead of jumping to the first.
{
  const originalText = "the cat sat. the cat ran";
  const original = scene(1, "One", originalText);
  const second = originalText.lastIndexOf("cat");
  const draft = createSingleFieldCommentDraft(original, "content", second, second + 3)!;
  const changed = scene(1, "One", "the cat slept. then the cat ran");
  const expected = changed.content.lastIndexOf("cat");
  equal("duplicate quote context chooses intended occurrence", commentSpans(fromDraft(1, draft), [changed]).map((s) => [s.fromOffset, s.toOffset]), [[expected, expected + 3]]);

  const legacy = comment(2, anchor(1, "content", second, 1, "content", second + 3), "cat");
  equal("duplicate quote without context chooses nearest", commentSpans(legacy, [changed]).map((s) => [s.fromOffset, s.toOffset]), [[expected, expected + 3]]);
}

// Red-team cases carried over from the proven flat-document engine.
{
  const repeatedLandmark = comment(
    3,
    anchor(1, "content", 8, 1, "content", 11, "the cat ", ". the cat sat"),
    "ran",
  );
  const changed = scene(1, "One", "the cat fled. the cat sat");
  const located = locateComment(repeatedLandmark, [changed]);
  check("repeated prefix pairs with the correct suffix", located != null && changed.content.slice(located.fromOffset, located.toOffset) === "fled");

  const boundary = comment(4, anchor(1, "content", 0, 1, "content", 3), "art");
  const boundarySpan = locateComment(boundary, [scene(1, "One", "restart now"), scene(2, "Two", "the art here")]);
  check("word boundary beats nearer embedded substring", boundarySpan?.sceneId === 2 && boundarySpan.fromOffset === 4);

  const ghost = comment(5, anchor(1, "content", 0, 1, "content", 2, "really ", " now"), "ok");
  const ghostSpan = locateComment(ghost, [scene(1, "One", "ok start, really ok now")]);
  check("wrong-context fast-path ghost is skipped", ghostSpan?.fromOffset === 17);

  const stable = comment(6, anchor(20, "content", 4, 20, "content", 8, "The ", " fell"), "rain");
  const duplicateScenes = [scene(10, "Duplicate", "The rain fell", 1), scene(15, "Inserted", "new", 2), scene(20, "Home", "The rain fell", 3)];
  check("stable scene id wins identical quote and context", locateComment(stable, duplicateScenes)?.sceneId === 20);
}

// If the quote is edited, two landmarks bracket the replacement. Deleting the
// selected text entirely leaves only an empty bracket, so the thread is orphaned.
{
  const original = scene(1, "One", "The rain had not stopped");
  const draft = createSingleFieldCommentDraft(original, "content", 4, 8)!;
  const edited = scene(1, "One", "The storm had not stopped");
  equal("edited quote bracketed by context", commentSpans(fromDraft(1, draft), [edited]).map((s) => [s.fromOffset, s.toOffset]), [[4, 9]]);

  const deleted = scene(1, "One", "The  had not stopped");
  equal("deleted quote paints no zero-width survivor", commentSpans(fromDraft(1, draft), [deleted]), []);
  equal("empty-bracket deletion is orphaned", findOrphanedCommentIds([fromDraft(1, draft)], [deleted]), [1]);
}

// One distinctive landmark is enough; a short common fragment is deliberately not.
{
  const original = scene(1, "One", "before distinctive rain after suffix");
  const start = original.content.indexOf("rain");
  const draft = createSingleFieldCommentDraft(original, "content", start, start + 4)!;
  const oneSided = scene(1, "One", "before distinctive storm completely changed");
  const span = locateComment(fromDraft(1, draft), [oneSided]);
  check("strong one-sided context survives", span?.fromOffset === oneSided.content.indexOf("storm"));

  const weak = comment(2, anchor(1, "content", 4, 1, "content", 8, "The ", " was"), "rain");
  check("weak one-sided context does not false-anchor", commentSpans(weak, [scene(1, "One", "The weather is calm")]).length === 0);
}

// A multi-paragraph selection remains one field-local span, including newlines.
{
  const text = "alpha\nbeta\ngamma";
  const current = scene(1, "One", text);
  const from = text.indexOf("pha");
  const to = text.indexOf("mma") + 3;
  const draft = createSingleFieldCommentDraft(current, "content", from, to)!;
  check("multi-paragraph quote retains newlines", draft.quote === "pha\nbeta\ngamma");
  equal("multi-paragraph content paints one scoped span", commentSpans(fromDraft(1, draft), [current]).map((s) => [s.sceneId, s.field, s.fromOffset, s.toOffset]), [[1, "content", from, to]]);
}

// Imported title→content and cross-scene ranges paint one span per traversed field.
{
  const scenes = [
    scene(1, "Chapter One", "Rain began softly", 1),
    scene(2, "Chapter Two", "and it ends right there", 2),
  ];
  const acrossFields = comment(10, anchor(1, "title", 8, 1, "content", 4, "Chapter ", " began"), "One\nRain");
  equal(
    "cross-field range paints title and content",
    commentSpans(acrossFields, scenes).map((s) => [s.sceneId, s.field, s.fromOffset, s.toOffset]),
    [[1, "title", 8, 11], [1, "content", 0, 4]],
  );

  const startText = "The story starts here";
  scenes[0] = scene(1, "Chapter One", startText, 1);
  const acrossScenes = comment(
    11,
    anchor(1, "content", 4, 2, "content", 11, "The ", " right there"),
    "story starts here\nChapter Two\nand it ends",
    true,
  );
  equal(
    "cross-scene range paints every intervening field",
    commentSpans(acrossScenes, scenes).map((s) => [s.sceneId, s.field, s.fromOffset, s.toOffset, s.resolved]),
    [
      [1, "content", 4, startText.length, true],
      [2, "title", 0, "Chapter Two".length, true],
      [2, "content", 0, 11, true],
    ],
  );
}

// Stable scene ids make ranges independent of input order; sort_order determines
// manuscript order. A newly inserted field is included in the live range.
{
  const first = scene(20, "First", "start edge", 10);
  const inserted = scene(25, "Inserted", "middle", 20);
  const last = scene(30, "Last", "end edge", 30);
  const value = comment(12, anchor(20, "content", 0, 30, "content", 3), "start edge\nend");
  const spans = commentSpans(value, [last, inserted, first]);
  equal(
    "scene order derives from sort_order, not caller order",
    spans.map((s) => [s.sceneId, s.field]),
    [[20, "content"], [25, "title"], [25, "content"], [30, "title"], [30, "content"]],
  );
}

// Each edge relocates independently; a surviving edge preserves the discussion.
{
  const original = [scene(1, "One", "prefix START", 1), scene(2, "Two", "END suffix", 2)];
  const value = comment(13, anchor(1, "content", 7, 2, "content", 3, "prefix ", " suffix"), "START\nEND");
  const moved = [scene(1, "One", "insert prefix START", 1), scene(2, "Two", "END suffix", 2)];
  check("cross-range start edge relocates", commentSpans(value, moved)[0]?.fromOffset === moved[0]!.content.indexOf("START"));

  const oneEdge = [scene(1, "One", "nothing remains", 1), scene(2, "Two", "END suffix", 2)];
  equal("one surviving cross-range edge is retained", commentSpans(value, oneEdge).map((s) => [s.sceneId, s.field, s.fromOffset, s.toOffset]), [[2, "content", 0, 3]]);
  check("one-edge survivor is not orphaned", findOrphanedCommentIds([value], oneEdge).length === 0);
}

// Legacy cross-field payloads without a separator retain structural endpoints
// rather than searching the same ambiguous quote twice.
{
  const current = [scene(1, "Title", "content", 1), scene(2, "Other", "tail", 2)];
  const legacy = comment(14, anchor(1, "content", 2, 2, "title", 3), "opaque legacy quote");
  equal(
    "legacy cross-field anchor uses structural edges",
    commentSpans(legacy, current).map((s) => [s.sceneId, s.field, s.fromOffset, s.toOffset]),
    [[1, "content", 2, 7], [2, "title", 0, 3]],
  );
}

// Empty-quote/zero-width legacy anchors survive and are snapped away from a
// surrogate split if surrounding text changed at the old offset.
{
  const point = comment(15, anchor(1, "content", 2, 1, "content", 2), "");
  equal("legacy point stays zero-width at a valid UTF-16 boundary", commentSpans(point, [scene(1, "One", "A😀B")]).map((s) => [s.fromOffset, s.toOffset]), [[1, 1]]);
  check("quote-less legacy point remains non-orphaned", findOrphanedCommentIds([point], [scene(1, "One", "A😀B")]).length === 0);
  check("quote-less legacy point never emits an invalid persistence patch", reconciledCommentPatch(point, [scene(1, "One", "A😀B")]) == null);

  const range = comment(16, anchor(1, "content", 1, 1, "content", 99), "");
  equal("quote-less structural range clamps safely", commentSpans(range, [scene(1, "One", "abc")]).map((s) => [s.fromOffset, s.toOffset]), [[1, 3]]);
}

// A quote may be moved wholesale to a different scene; exact text + context wins.
{
  const original = scene(1, "One", "before portable quote after", 1);
  const from = original.content.indexOf("portable quote");
  const draft = fromDraft(17, createSingleFieldCommentDraft(original, "content", from, from + "portable quote".length)!);
  const scenes = [scene(1, "One", "removed", 1), scene(2, "Two", "before portable quote after", 2)];
  const span = locateComment(draft, scenes);
  check("exact quote can relocate across scene scope", span?.sceneId === 2 && span.field === "content");
}

// Genuine disappearance is orphaned, while an empty scene list is only a load transient.
{
  const gone = comment(18, anchor(1, "content", 4, 1, "content", 8, "The ", " fell"), "rain");
  equal("genuine removal has no spans", commentSpans(gone, [scene(1, "One", "unrelated")]), []);
  equal("genuine removal is orphaned", findOrphanedCommentIds([gone], [scene(1, "One", "unrelated")]), [18]);
  equal("empty scene list never declares orphans", findOrphanedCommentIds([gone], []), []);
}

// Bulk reconciliation preserves comment metadata and emits all field-local spans.
{
  const current = [scene(1, "Title", "alpha beta")];
  const a = comment(21, anchor(1, "title", 0, 1, "title", 5), "Title");
  const b = comment(22, anchor(1, "content", 6, 1, "content", 10), "beta", false);
  equal(
    "bulk reconciliation emits both comments",
    reconcileCommentSpans([a, b], current).map((s) => [s.commentId, s.sceneId, s.field, s.fromOffset, s.toOffset]),
    [[21, 1, "title", 0, 5], [22, 1, "content", 6, 10]],
  );
}

// Reconciliation patches only complete, materially changed ranges. They update
// both location and quote so subsequent passes use the new live snapshot.
{
  const original = scene(1, "One", "The rain had not stopped");
  const rain = fromDraft(30, createSingleFieldCommentDraft(original, "content", 4, 8)!);
  check("unchanged complete range needs no persistence patch", reconciledCommentPatch(rain, [original]) == null);

  const shifted = scene(1, "One", "Oh, The rain had not stopped");
  const shiftedPatch = reconciledCommentPatch(rain, [shifted]);
  equal(
    "relocated range patch refreshes offsets and context",
    shiftedPatch,
    {
      anchor: anchor(1, "content", 8, 1, "content", 12, "Oh, The ", " had not stopped"),
      quote: "rain",
    },
  );

  const edited = scene(1, "One", "The storm had not stopped");
  const editedPatch = reconciledCommentPatch(rain, [edited]);
  equal("edited range patch stores its live quote", [editedPatch?.anchor?.from_offset, editedPatch?.anchor?.to_offset, editedPatch?.quote], [4, 9, "storm"]);

  const sameLengthEdit = scene(1, "One", "The hail had not stopped");
  const sameLengthPatch = reconciledCommentPatch(rain, [sameLengthEdit]);
  equal(
    "same-offset in-span edit persists refreshed quote",
    sameLengthPatch,
    {
      anchor: anchor(1, "content", 4, 1, "content", 8, "The ", " had not stopped"),
      quote: "hail",
    },
  );
  const afterInSpanEdit: InlineCommentDTO = {
    ...rain,
    anchor: sameLengthPatch?.anchor ?? rain.anchor,
    quote: sameLengthPatch?.quote ?? rain.quote,
  };
  const editedAround = scene(1, "One", "Oh, The hail had not stopped");
  const aroundPatch = reconciledCommentPatch(afterInSpanEdit, [editedAround]);
  equal(
    "subsequent around-edit relocates from refreshed quote",
    aroundPatch,
    {
      anchor: anchor(1, "content", 8, 1, "content", 12, "Oh, The ", " had not stopped"),
      quote: "hail",
    },
  );

  const changedContext = scene(1, "One", "Our rain sank!");
  const contextPatch = reconciledCommentPatch(rain, [changedContext]);
  equal(
    "same range and quote refresh context with anchor-only patch",
    contextPatch,
    { anchor: anchor(1, "content", 4, 1, "content", 8, "Our ", " sank!") },
  );
  check("context-only patch omits quote", contextPatch != null && !("quote" in contextPatch));

  const deleted = scene(1, "One", "The  had not stopped");
  const deletedPatch = reconciledCommentPatch(rain, [deleted]);
  check("total deletion never persists an empty-bracket anchor", deletedPatch == null);
}

// Complete cross-field patches rebuild the canonical newline-joined quote;
// one-edge rescues and orphans remain paint-only and never destroy durable data.
{
  const originalScenes = [scene(1, "Chapter One", "Rain began", 1)];
  const imported = comment(31, anchor(1, "title", 8, 1, "content", 4, "Chapter ", " began"), "One\nRain");
  const changedScenes = [scene(1, "New Chapter One", "Rain poured", 1)];
  const patch = reconciledCommentPatch(imported, changedScenes);
  equal(
    "cross-field patch refreshes both edges and joined quote",
    patch,
    {
      anchor: anchor(1, "title", 12, 1, "content", 4, "New Chapter ", " poured"),
      quote: "One\nRain",
    },
  );

  const cross = comment(32, anchor(1, "content", 7, 2, "content", 3, "prefix ", " suffix"), "START\nEND");
  const oneEdge = [scene(1, "One", "gone", 1), scene(2, "Two", "END suffix", 2)];
  check("partial-edge rescue is never persisted", reconciledCommentPatch(cross, oneEdge) == null);
  check("orphan is never persisted", reconciledCommentPatch(cross, [scene(1, "One", "gone", 1), scene(2, "Two", "also gone", 2)]) == null);
}

// An untouched imported range keeps its source TextQuote even when canonical Pro
// field joining differs. Once an endpoint truly relocates, the patch captures the
// exact field slices with one newline separator per traversed field.
{
  const value = {
    ...comment(33, anchor(1, "content", 0, 3, "content", 3), "start\nEnd\nend"),
    source_id: "whiteboard-comment-33",
  };
  const scenes = [
    scene(1, "Start", "start", 1),
    scene(2, "Middle", "middle", 2),
    scene(3, "End", "end tail", 3),
  ];
  check("untouched imported cross-scene quote is not rewritten", reconciledCommentPatch(value, scenes) == null);

  const nativeCross = comment(
    35,
    anchor(1, "content", 0, 3, "content", 3, "", " tail"),
    "start\nMiddle\nmiddle before\nEnd\nend",
  );
  const nativePatch = reconciledCommentPatch(nativeCross, scenes);
  equal(
    "same-range native cross-scene edit refreshes canonical quote",
    nativePatch?.quote,
    "start\nMiddle\nmiddle\nEnd\nend",
  );

  const stale = comment(34, anchor(1, "content", 2, 3, "content", 3), "start\nEnd\nend");
  const patch = reconciledCommentPatch(stale, scenes);
  equal("cross-scene quote joins every field slice", patch?.quote, "start\nMiddle\nmiddle\nEnd\nend");
  equal("cross-scene patch retains endpoint scopes", patch?.anchor && [patch.anchor.start_scene_id, patch.anchor.start_field, patch.anchor.end_scene_id, patch.anchor.end_field], [1, "content", 3, "content"]);
}

// ProseMirror's paragraph tokens are translated to/from the same plain UTF-16
// coordinate space as comment anchors, including astral text and empty lines.
{
  const doc = proseDoc(["A😀B", "second", "", "tail"]);
  equal(
    "PM positions map to UTF-16 plain offsets",
    [1, 2, 4, 5, 7, 13, 15, 17].map((position) => proseDocumentPositionToTextOffset(doc, position)),
    [0, 1, 3, 4, 5, 11, 12, 13],
  );
  equal(
    "astral highlight stays on complete surrogate pair",
    proseCommentDocumentRanges(doc, 1, 3),
    [{ from: 2, to: 4 }],
  );
  equal(
    "multi-paragraph highlight splits at paragraph boundaries",
    proseCommentDocumentRanges(doc, 3, 15),
    [{ from: 4, to: 5 }, { from: 7, to: 13 }, { from: 17, to: 19 }],
  );
  equal(
    "zero-width offset in an empty paragraph survives",
    proseCommentDocumentRanges(doc, 12, 12),
    [{ from: 15, to: 15 }],
  );
}

console.log(`Pro comment anchor tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.log(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} Pro comment anchor test(s) failed`);
console.log("PRO COMMENT ANCHORS: PASS");
