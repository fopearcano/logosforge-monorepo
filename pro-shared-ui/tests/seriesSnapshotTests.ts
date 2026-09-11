import type { ApiClient } from "../src/adapters/api";
import { loadSeriesSnapshot } from "../src/hooks/seriesSnapshot";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

{
  const calls: string[] = [];
  const api = {
    listSeasons: async (projectId: number) => { calls.push(`seasons:${projectId}`); return [{ id: 1, season_number: 1, title: "One" }]; },
    listEpisodes: async (projectId: number) => { calls.push(`episodes:${projectId}`); return [{ id: 2, season_id: 1, episode_number: 1, title: "Pilot" }]; },
    listSeriesArcs: async (projectId: number) => { calls.push(`arcs:${projectId}`); return [{ id: 3, title: "Arc" }]; },
  } as unknown as ApiClient;
  const snapshot = await loadSeriesSnapshot(api, 42);
  check("all three Series endpoints are requested", calls.sort().join(",") === "arcs:42,episodes:42,seasons:42");
  check("successful values publish as one snapshot", snapshot.seasons.length === 1 && snapshot.episodes.length === 1 && snapshot.arcs.length === 1);
}

{
  const api = {
    listSeasons: async () => [{ id: 1 }],
    listEpisodes: async () => { throw new Error("episodes unavailable"); },
    listSeriesArcs: async () => [{ id: 3 }],
  } as unknown as ApiClient;
  let message = "";
  try { await loadSeriesSnapshot(api, 7); }
  catch (error) { message = error instanceof Error ? error.message : String(error); }
  check("one failed endpoint rejects the whole snapshot", message === "episodes unavailable");
}

console.log(`Series snapshot tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} Series snapshot test(s) failed`);
console.log("SERIES SNAPSHOT TESTS: PASS");
