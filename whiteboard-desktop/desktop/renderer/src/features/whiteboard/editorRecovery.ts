import type { WhiteboardBlock } from './types';

/**
 * Choose the snapshot used when the editor mounts or remounts.
 *
 * A render boundary can temporarily unmount TipTap without unmounting the
 * document owner. In that case the in-memory blocks are newer than the document
 * payload originally loaded from the backend, so recovery must prefer them.
 * During a real document switch, however, the live snapshot can still belong to
 * the previous document for one render and must not cross that boundary.
 */
export function editorRecoveryBlocks(
  activeDocumentId: string | null,
  liveDocumentId: string | null,
  liveBlocks: WhiteboardBlock[],
  loadedBlocks: WhiteboardBlock[],
): WhiteboardBlock[] {
  return activeDocumentId !== null && activeDocumentId === liveDocumentId
    ? liveBlocks
    : loadedBlocks;
}
