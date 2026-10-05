import type {
  CanvasPlotFrameDTO,
  CanvasPlotNodeDTO,
} from "@logosforge/ui-contracts";

export const CANVAS_MIN_ZOOM = 0.25;
export const CANVAS_MAX_ZOOM = 4;
export const CANVAS_NODE_MIN_WIDTH = 120;
export const CANVAS_NODE_MIN_HEIGHT = 72;
export const CANVAS_FRAME_MIN_WIDTH = 160;
export const CANVAS_FRAME_MIN_HEIGHT = 110;

export interface CanvasPoint {
  x: number;
  y: number;
}

export interface CanvasSize {
  width: number;
  height: number;
}

export interface CanvasRect extends CanvasPoint, CanvasSize {}

export interface CanvasViewport {
  zoom: number;
  cx: number;
  cy: number;
}

export const DEFAULT_CANVAS_VIEWPORT: CanvasViewport = {
  zoom: 1,
  cx: 0,
  cy: 0,
};

const finite = (value: unknown, fallback: number): number => (
  typeof value === "number" && Number.isFinite(value) ? value : fallback
);

export function clampCanvasZoom(value: number): number {
  return Math.max(CANVAS_MIN_ZOOM, Math.min(CANVAS_MAX_ZOOM, finite(value, 1)));
}

export function parseCanvasViewport(value: unknown): CanvasViewport {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { ...DEFAULT_CANVAS_VIEWPORT };
  }
  const candidate = value as Record<string, unknown>;
  return {
    zoom: clampCanvasZoom(finite(candidate.zoom, DEFAULT_CANVAS_VIEWPORT.zoom)),
    cx: finite(candidate.cx, DEFAULT_CANVAS_VIEWPORT.cx),
    cy: finite(candidate.cy, DEFAULT_CANVAS_VIEWPORT.cy),
  };
}

export function screenToWorld(
  point: CanvasPoint,
  viewport: CanvasViewport,
  size: CanvasSize,
): CanvasPoint {
  return {
    x: viewport.cx + (point.x - size.width / 2) / viewport.zoom,
    y: viewport.cy + (point.y - size.height / 2) / viewport.zoom,
  };
}

export function worldToScreen(
  point: CanvasPoint,
  viewport: CanvasViewport,
  size: CanvasSize,
): CanvasPoint {
  return {
    x: (point.x - viewport.cx) * viewport.zoom + size.width / 2,
    y: (point.y - viewport.cy) * viewport.zoom + size.height / 2,
  };
}

/** Pan by screen-space pixels while preserving the world-space camera model. */
export function panCanvasViewport(
  viewport: CanvasViewport,
  deltaScreen: CanvasPoint,
): CanvasViewport {
  return {
    ...viewport,
    cx: viewport.cx - deltaScreen.x / viewport.zoom,
    cy: viewport.cy - deltaScreen.y / viewport.zoom,
  };
}

/** Zoom around a screen-space anchor without moving the world point beneath it. */
export function zoomCanvasViewportAt(
  viewport: CanvasViewport,
  nextZoom: number,
  anchorScreen: CanvasPoint,
  size: CanvasSize,
): CanvasViewport {
  const anchorWorld = screenToWorld(anchorScreen, viewport, size);
  const zoom = clampCanvasZoom(nextZoom);
  return {
    zoom,
    cx: anchorWorld.x - (anchorScreen.x - size.width / 2) / zoom,
    cy: anchorWorld.y - (anchorScreen.y - size.height / 2) / zoom,
  };
}

export function canvasWorldTransform(
  viewport: CanvasViewport,
  size: CanvasSize,
): string {
  const tx = size.width / 2 - viewport.cx * viewport.zoom;
  const ty = size.height / 2 - viewport.cy * viewport.zoom;
  return `translate(${tx}px, ${ty}px) scale(${viewport.zoom})`;
}

export function resizeCanvasRect(
  rect: CanvasRect,
  deltaWorld: CanvasPoint,
  kind: "node" | "frame",
): CanvasRect {
  const minWidth = kind === "node" ? CANVAS_NODE_MIN_WIDTH : CANVAS_FRAME_MIN_WIDTH;
  const minHeight = kind === "node" ? CANVAS_NODE_MIN_HEIGHT : CANVAS_FRAME_MIN_HEIGHT;
  return {
    ...rect,
    width: Math.max(minWidth, rect.width + deltaWorld.x),
    height: Math.max(minHeight, rect.height + deltaWorld.y),
  };
}

export function moveCanvasRect(rect: CanvasRect, deltaWorld: CanvasPoint): CanvasRect {
  return {
    ...rect,
    x: rect.x + deltaWorld.x,
    y: rect.y + deltaWorld.y,
  };
}

function boundaryPoint(rect: CanvasRect, toward: CanvasPoint): CanvasPoint {
  const center = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  const dx = toward.x - center.x;
  const dy = toward.y - center.y;
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) return center;
  const scale = Math.min(
    Math.abs(dx) < 1e-9 ? Number.POSITIVE_INFINITY : (rect.width / 2) / Math.abs(dx),
    Math.abs(dy) < 1e-9 ? Number.POSITIVE_INFINITY : (rect.height / 2) / Math.abs(dy),
  );
  return { x: center.x + dx * scale, y: center.y + dy * scale };
}

export interface CanvasLinkGeometry {
  source: CanvasPoint;
  target: CanvasPoint;
  midpoint: CanvasPoint;
  path: string;
}

export function canvasLinkGeometry(source: CanvasRect, target: CanvasRect): CanvasLinkGeometry {
  const sourceCenter = { x: source.x + source.width / 2, y: source.y + source.height / 2 };
  const targetCenter = { x: target.x + target.width / 2, y: target.y + target.height / 2 };
  const start = boundaryPoint(source, targetCenter);
  const end = boundaryPoint(target, sourceCenter);
  const dx = end.x - start.x;
  const bend = Math.max(28, Math.abs(dx) * 0.38);
  const c1 = { x: start.x + Math.sign(dx || 1) * bend, y: start.y };
  const c2 = { x: end.x - Math.sign(dx || 1) * bend, y: end.y };
  return {
    source: start,
    target: end,
    midpoint: { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 },
    path: `M ${start.x} ${start.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${end.x} ${end.y}`,
  };
}

export function canvasContentBounds(
  nodes: readonly Pick<CanvasPlotNodeDTO, "x" | "y" | "width" | "height">[],
  frames: readonly Pick<CanvasPlotFrameDTO, "x" | "y" | "width" | "height">[],
): CanvasRect | null {
  const items = [...nodes, ...frames];
  if (items.length === 0) return null;
  const left = Math.min(...items.map((item) => item.x));
  const top = Math.min(...items.map((item) => item.y));
  const right = Math.max(...items.map((item) => item.x + item.width));
  const bottom = Math.max(...items.map((item) => item.y + item.height));
  return { x: left, y: top, width: right - left, height: bottom - top };
}

export function fitCanvasViewport(
  bounds: CanvasRect | null,
  size: CanvasSize,
  padding = 60,
): CanvasViewport {
  if (!bounds || size.width <= 0 || size.height <= 0) return { ...DEFAULT_CANVAS_VIEWPORT };
  const availableWidth = Math.max(1, size.width - padding * 2);
  const availableHeight = Math.max(1, size.height - padding * 2);
  const zoom = clampCanvasZoom(Math.min(
    availableWidth / Math.max(bounds.width, 1),
    availableHeight / Math.max(bounds.height, 1),
  ));
  return {
    zoom,
    cx: bounds.x + bounds.width / 2,
    cy: bounds.y + bounds.height / 2,
  };
}
