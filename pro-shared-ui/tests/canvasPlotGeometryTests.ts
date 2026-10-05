import {
  CANVAS_MAX_ZOOM,
  CANVAS_MIN_ZOOM,
  canvasContentBounds,
  canvasLinkGeometry,
  fitCanvasViewport,
  panCanvasViewport,
  parseCanvasViewport,
  resizeCanvasRect,
  screenToWorld,
  worldToScreen,
  zoomCanvasViewportAt,
} from "../src/components/spatialcanvas/canvasPlotGeometry";

let assertions = 0;
function check(value: unknown, message: string): asserts value {
  assertions += 1;
  if (!value) throw new Error(message);
}
const near = (left: number, right: number) => Math.abs(left - right) < 1e-8;

const size = { width: 800, height: 600 };
const viewport = { zoom: 2, cx: 100, cy: -40 };
const world = { x: 175, y: 10 };
const screen = worldToScreen(world, viewport, size);
check(screen.x === 550 && screen.y === 400, "world coordinates must project through the centered camera");
const roundTrip = screenToWorld(screen, viewport, size);
check(near(roundTrip.x, world.x) && near(roundTrip.y, world.y), "screen/world conversion must round-trip");

const panned = panCanvasViewport(viewport, { x: 80, y: -20 });
check(panned.cx === 60 && panned.cy === -30, "screen-space pan must account for zoom");

const anchor = { x: 630, y: 145 };
const anchorBefore = screenToWorld(anchor, viewport, size);
const zoomed = zoomCanvasViewportAt(viewport, 3.5, anchor, size);
const anchorAfter = screenToWorld(anchor, zoomed, size);
check(near(anchorBefore.x, anchorAfter.x) && near(anchorBefore.y, anchorAfter.y), "cursor-anchored zoom must preserve the world point under the cursor");
check(zoomCanvasViewportAt(viewport, 99, anchor, size).zoom === CANVAS_MAX_ZOOM, "zoom must clamp at the maximum");
check(zoomCanvasViewportAt(viewport, 0.01, anchor, size).zoom === CANVAS_MIN_ZOOM, "zoom must clamp at the minimum");

const parsed = parseCanvasViewport({ zoom: 99, cx: 12, cy: Number.NaN });
check(parsed.zoom === CANVAS_MAX_ZOOM && parsed.cx === 12 && parsed.cy === 0, "persisted view parsing must clamp zoom and reject non-finite coordinates");
check(parseCanvasViewport("bad").zoom === 1, "malformed persisted view state must use the default camera");

const tinyNode = resizeCanvasRect({ x: 0, y: 0, width: 130, height: 80 }, { x: -100, y: -100 }, "node");
check(tinyNode.width === 120 && tinyNode.height === 72, "node resizing must retain accessible minimum dimensions");
const tinyFrame = resizeCanvasRect({ x: 0, y: 0, width: 170, height: 120 }, { x: -100, y: -100 }, "frame");
check(tinyFrame.width === 160 && tinyFrame.height === 110, "frame resizing must retain usable minimum dimensions");

const geometry = canvasLinkGeometry(
  { x: 0, y: 0, width: 200, height: 100 },
  { x: 400, y: 0, width: 200, height: 100 },
);
check(geometry.source.x === 200 && geometry.target.x === 400, "connection endpoints must meet card boundaries rather than card centers");
check(geometry.path.startsWith("M 200 50 C"), "connection geometry must produce a stable cubic path");

const bounds = canvasContentBounds(
  [{ x: -100, y: 20, width: 200, height: 80 }],
  [{ x: 250, y: -200, width: 300, height: 400 }],
);
check(bounds?.x === -100 && bounds.y === -200 && bounds.width === 650 && bounds.height === 400, "content bounds must include nodes and frames");
const fitted = fitCanvasViewport(bounds, size, 50);
check(fitted.cx === 225 && fitted.cy === 0 && near(fitted.zoom, 700 / 650), "fit view must center and scale all content with padding");

console.log(`${assertions} Canvas Plot geometry assertions passed.`);
