import { Placeholder } from "./_Placeholder";

/**
 * Narrative intelligence. The Narrative Dashboard (mission control) is
 * implemented from the Project OS handoff page — re-exported from ./projectos.
 * The standalone HUD widgets remain stubs until their handoff.
 */
export { NarrativeDashboard } from "./projectos";

/** Compact health HUD (high-level status indicators). */
export const StoryHealthHud = () => <Placeholder name="Story Health HUD" screenLabel="story-health-hud" ticket="06" />;
/** Subtle pacing / rhythm analysis panel. */
export const PacingInsights = () => <Placeholder name="Pacing Insights" screenLabel="pacing-insights" ticket="06" />;
/** Beat / Act / Tag coverage + distribution views. */
export const CoverageAnalysis = () => <Placeholder name="Beat / Act / Tag Analysis" screenLabel="coverage-analysis" ticket="06" />;
/** Character arc + presence/balance charts. */
export const CharacterBalance = () => <Placeholder name="Character Arc & Balance" screenLabel="character-balance" ticket="06" />;
