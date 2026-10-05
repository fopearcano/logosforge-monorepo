export interface FloatingPanelPosition {
  x: number;
  y: number;
}

export interface FloatingPanelViewport {
  width: number;
  height: number;
}

interface FloatingPanelInitialOptions {
  side: 'left' | 'right';
  top?: number;
  preferred?: FloatingPanelPosition;
}

const EDGE_GAP = 8;
const HEADER_VISIBLE = 56;

/** Keep the whole panel horizontally reachable and at least its header visible vertically. */
export function clampFloatingPanelPosition(
  position: FloatingPanelPosition,
  panelWidth: number,
  viewport: FloatingPanelViewport,
): FloatingPanelPosition {
  const usableWidth = Math.max(0, viewport.width - EDGE_GAP * 2);
  const renderedWidth = Math.min(panelWidth, usableWidth);
  const maxX = Math.max(EDGE_GAP, viewport.width - renderedWidth - EDGE_GAP);
  const maxY = Math.max(EDGE_GAP, viewport.height - HEADER_VISIBLE);
  return {
    x: Math.min(Math.max(EDGE_GAP, Math.round(position.x)), maxX),
    y: Math.min(Math.max(EDGE_GAP, Math.round(position.y)), maxY),
  };
}

export function defaultFloatingPanelPosition(
  panelWidth: number,
  viewport: FloatingPanelViewport,
  side: 'left' | 'right',
  top = 64,
): FloatingPanelPosition {
  return clampFloatingPanelPosition(
    { x: side === 'left' ? 20 : viewport.width - panelWidth - 20, y: top },
    panelWidth,
    viewport,
  );
}

/** Use a contextual anchor when supplied; otherwise fall back to the usual edge position. */
export function initialFloatingPanelPosition(
  panelWidth: number,
  viewport: FloatingPanelViewport,
  options: FloatingPanelInitialOptions,
): FloatingPanelPosition {
  if (options.preferred) {
    return clampFloatingPanelPosition(options.preferred, panelWidth, viewport);
  }
  return defaultFloatingPanelPosition(panelWidth, viewport, options.side, options.top);
}
