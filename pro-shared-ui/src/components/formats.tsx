/**
 * Format engines, Stages, Voice & Export (design Ticket 07) — implemented for
 * real from the Claude Design handoff page (./formatpanels). `PipelineConfirm`
 * aliases `ModeReviewDashboard`: the design's "Mode Review + Pipeline Confirm" is
 * one panel with both halves. `ModeReskin` (the five-mode re-skin hero) and
 * `CrossCutting` (launchpad + settings) are new surfaces from this page.
 */
export {
  ModeReskin,
  StagesPanel,
  VoiceHud,
  PageCanvas,
  ExportDialog,
  ModeReviewDashboard,
  ModeReviewDashboard as PipelineConfirm,
  CrossCutting,
} from "./formatpanels";
