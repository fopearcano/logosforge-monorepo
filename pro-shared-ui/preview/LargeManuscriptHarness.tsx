import type { ApiClient, PlatformAdapter } from "../src";
import type { SceneDTO } from "@logosforge/ui-contracts";
import { StudioProvider, ManuscriptEditor } from "../src";
import { createMockApiClient } from "./mockApi";

const baseApi = createMockApiClient();
const largeScenes: SceneDTO[] = Array.from({ length: 180 }, (_, index) => ({
  id: 10_000 + index,
  title: `Scene ${index + 1}`,
  content: `Scene ${index + 1} opens with a concrete image.\n\nThe character makes a choice that changes the direction of the chapter.\n\nA final beat carries the reader forward.`,
  summary: `Synthetic scalability scene ${index + 1}`,
  synopsis: "",
  goal: "",
  conflict: "",
  outcome: "",
  beat: "",
  act: `Act ${Math.floor(index / 60) + 1}`,
  chapter: String(Math.floor(index / 6) + 1),
  plotline: index % 2 === 0 ? "A" : "B",
  color_label: "",
  tags: [],
  sort_order: index,
  order_index: index,
  character_ids: [],
  place_ids: [],
  who_knows_what: "",
  revision: `large-${index}`,
}));

const api: ApiClient = {
  ...baseApi,
  listScenes: async () => largeScenes.map((scene) => ({ ...scene })),
};
const platform: PlatformAdapter = {
  isDesktop: false,
  openFile: async () => ({ canceled: true }),
  saveFile: async () => ({ canceled: true }),
  openExternal: async () => undefined,
};

/** Browser-only scalability fixture (`?large-manuscript-harness`). */
export function LargeManuscriptHarness() {
  return (
    <div style={{ width: "100vw", height: "100vh", background: "#04060a" }}>
      <StudioProvider services={{ api, platform }} writingMode="novel" projectId={1}>
        <ManuscriptEditor />
      </StudioProvider>
    </div>
  );
}
