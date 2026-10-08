/** Browser-selection helpers for native comments spanning ProseMirror roots. */

function stripDecorationWidgets(fragment: DocumentFragment): void {
  fragment.querySelectorAll(".pm-comment-caret").forEach((element) => element.remove());
}

function visibleTextLength(node: Node): number {
  if (node.nodeType === 1 && (node as Element).matches(".pm-comment-caret")) return 0;
  const clone = node.cloneNode(true);
  if (clone.nodeType === 11) stripDecorationWidgets(clone as DocumentFragment);
  else if (clone.nodeType === 1) (clone as Element).querySelectorAll(".pm-comment-caret").forEach((element) => element.remove());
  return clone.textContent?.length ?? 0;
}

/** Return the ProseMirror content root containing a browser-selection endpoint. */
export function proseRootForDomPoint(node: Node | null): HTMLElement | null {
  if (!node) return null;
  const element = node.nodeType === 1 ? node as Element : node.parentElement;
  return element?.closest<HTMLElement>("[data-prose]") ?? null;
}

export interface ProseDomPoint {
  container: Node;
  offset: number;
}

/** Resolve the nearest editable DOM point at viewport coordinates. */
export function proseDomPointFromViewport(
  root: HTMLElement,
  x: number,
  y: number,
): ProseDomPoint | null {
  type CaretDocument = Document & {
    caretPositionFromPoint?: (left: number, top: number) => { offsetNode: Node; offset: number } | null;
    caretRangeFromPoint?: (left: number, top: number) => Range | null;
  };
  const ownerDocument = root.ownerDocument as CaretDocument;
  const position = ownerDocument.caretPositionFromPoint?.(x, y);
  const point = position
    ? { container: position.offsetNode, offset: position.offset }
    : (() => {
        const range = ownerDocument.caretRangeFromPoint?.(x, y);
        return range ? { container: range.startContainer, offset: range.startOffset } : null;
      })();
  if (!point || (point.container !== root && !root.contains(point.container))) return null;
  return point;
}

/**
 * Convert a DOM selection point inside a `[data-prose]` root to the plain-text
 * UTF-16 coordinate used by the comment contract. ProseMirror stores one
 * paragraph per line; direct children are therefore joined with one newline.
 * Decoration widgets are deliberately ignored because they are presentation,
 * not manuscript text.
 */
export function proseDomPointToTextOffset(
  root: HTMLElement,
  container: Node,
  offset: number,
): number | null {
  if (container !== root && !root.contains(container)) return null;
  if (!Number.isInteger(offset) || offset < 0) return null;

  const blocks = Array.from(root.children).filter((element) => !element.matches(".pm-comment-caret"));
  if (!blocks.length) return container === root && offset === 0 ? 0 : null;

  if (container === root) {
    if (offset > root.childNodes.length) return null;
    const passed = blocks.filter((block) => {
      const childIndex = Array.prototype.indexOf.call(root.childNodes, block) as number;
      return childIndex >= 0 && childIndex < offset;
    });
    const separators = Math.min(passed.length, Math.max(0, blocks.length - 1));
    return passed.reduce((total, block) => total + visibleTextLength(block), 0) + separators;
  }

  let directChild: Node | null = container;
  while (directChild?.parentNode && directChild.parentNode !== root) directChild = directChild.parentNode;
  if (!directChild || directChild.nodeType !== 1) return null;
  const directChildElement = directChild as Element;
  const blockIndex = blocks.indexOf(directChildElement);
  if (blockIndex < 0) return null;
  if (directChildElement.matches(".pm-comment-caret") || (container.nodeType === 1 && (container as Element).closest(".pm-comment-caret"))) return null;
  if (container.nodeType !== 1 && container.parentElement?.closest(".pm-comment-caret")) return null;

  let within = 0;
  try {
    const range = root.ownerDocument.createRange();
    range.setStart(directChildElement, 0);
    range.setEnd(container, offset);
    const fragment = range.cloneContents();
    stripDecorationWidgets(fragment);
    within = fragment.textContent?.length ?? 0;
  } catch {
    return null;
  }

  let total = blockIndex;
  for (let index = 0; index < blockIndex; index += 1) total += visibleTextLength(blocks[index]!);
  return total + within;
}
