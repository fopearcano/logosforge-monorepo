# Ticket 03 — Timeline, Plot & Knowledge Graph (the spatial canvases)

> Brief: §4.3 (timeline/plot), §4.8 (graph). Fills `src/components/spatial.tsx`
> (TimelinePanel, CanvasPlot, KnowledgeGraph). These are signature cinematic
> surfaces — make them beautiful.

## Goal
The spatial story views: lanes, a free plotting board, and a living knowledge
graph.

## Screens / panels
- **Timeline Panel** — plot-lane (horizontal, per-plotline) and chapter-column
  views; overlays you can toggle (tension / pacing / POV); light inline editing.
  Support Structural vs Custom ordering.
- **Canvas Plot** — a free, zoomable, pannable visual plotting board: scene cards
  on a 2D canvas, colored by plotline/label, draggable, with typed links.
- **Knowledge Graph** — an interactive narrative graph: nodes **sized by Story
  Gravity** (importance), edges typed; a **flow overlay** (story order); **focus
  mode** (explore from a node); a side list of orphans / weak-links → actionable
  cards. Show node/edge type + **confidence**.

## Key interactions
- Pan/zoom/drag; toggle overlays; switch ordering; focus a node; click a
  weak-link card → jump. Lanes accept drag-reorder.

## Data
`PlotBlockDTO` + `PlotSceneDTO`, `TimelineEventDTO` (scene-derived, with
character-states), and the derived knowledge-graph nodes/edges (typed, scored).

## Acceptance
Three distinct, gorgeous spatial canvases; dense data made navigable; the graph
feels like a story HUD, not a generic node editor.
