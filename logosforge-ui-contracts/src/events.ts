/**
 * Change-event names — mirror the core's `logosforge.api.events` broker, which
 * mirrors the desktop Qt bus. Delivered over SSE (`GET /api/events`) or polling
 * (`GET /api/events/poll`). Reactive panels subscribe and refetch the affected
 * domain.
 */

export const KNOWN_EVENTS = [
  "project_loaded",
  "project_data_changed",
  "scene_changed",
  "scenes_changed",
  "outline_changed",
  "plot_changed",
  "timeline_changed",
  "psyke_changed",
  "notes_changed",
  "characters_changed",
  "dashboard_changed",
  "assistant_action_completed",
] as const;

export type EventName = (typeof KNOWN_EVENTS)[number];

export interface EventMessage {
  id: number;
  event: EventName | "connected";
  project_id: number | null;
  data: Record<string, unknown>;
  ts: number;
}
