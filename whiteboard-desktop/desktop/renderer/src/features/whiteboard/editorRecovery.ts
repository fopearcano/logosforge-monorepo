import type { WhiteboardBlock } from './types';

/**
 * Choose the snapshot used when the editor mounts or remounts.
 *
 * A render boundary can temporarily unmount TipTap without unmounting the
 * document owner. In that case the in-memory blocks are newer than the document
 * payload originally loaded from the backend, so recovery must prefer them.
 * During a real document switch or an explicit same-document revision reload,
 * however, the live snapshot can still represent the superseded draft for one
 * render and must not cross that durable snapshot boundary.
 */
export function editorRecoveryBlocks(
  activeDocumentSnapshot: string | null,
  liveDocumentSnapshot: string | null,
  liveBlocks: WhiteboardBlock[],
  loadedBlocks: WhiteboardBlock[],
): WhiteboardBlock[] {
  return activeDocumentSnapshot !== null && activeDocumentSnapshot === liveDocumentSnapshot
    ? liveBlocks
    : loadedBlocks;
}
