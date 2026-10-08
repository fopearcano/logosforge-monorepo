import { useEffect } from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { WorkspaceShell } from "../src/components/shell/WorkspaceShell";
import { useSkin } from "../src/components/shell/SkinContext";
import {
  SKIN_IDS,
  SKIN_OPTIONS,
  resolveSkin,
  shellSkinVars,
  type SkinId,
} from "../src/components/shell/shellVars";

let assertions = 0;
function check(condition: unknown, message: string): asserts condition {
  assertions += 1;
  if (!condition) throw new Error(message);
}

check(SKIN_IDS.join(",") === "forge,paper,lamplit", "skin ids should remain stable persistence values");
check(SKIN_OPTIONS.map((option) => option.label).join(",") === "Forge,Paper,Lamplit", "skin labels should be user-facing names");
check(resolveSkin("forge") === "forge", "current Forge id should resolve");
check(resolveSkin("paper") === "paper", "current Paper id should resolve");
check(resolveSkin("lamplit") === "lamplit", "current Lamplit id should resolve");
check(resolveSkin("dark") === "forge", "legacy dark should migrate to Forge");
check(resolveSkin("light") === "paper", "legacy light should migrate to Paper");
check(resolveSkin("warm") === "lamplit", "legacy warm should migrate to Lamplit");
check(resolveSkin("unknown") === "forge" && resolveSkin(null) === "forge", "invalid skin values should fail safe to Forge");

const requiredVars = [
  "--void", "--base", "--panel", "--panel2", "--raised", "--txt", "--txt2", "--txt3", "--strong",
  "--line", "--line2", "--line-cy", "--on-accent", "--page-shadow", "--ui-font", "--display-font",
  "--ui-tracking", "--brand-tracking", "--control-radius", "--panel-radius", "--chrome-shadow", "--signal-glow",
  "--accent", "--accent-soft", "--blocking", "--warning", "--suggestion", "--opportunity",
] as const;
for (const skin of SKIN_IDS) {
  const vars = shellSkinVars("novel", skin) as Record<string, string>;
  check(requiredVars.every((name) => typeof vars[name] === "string" && vars[name].length > 0), `${skin} should provide the complete semantic skin contract`);
}
const forgeVars = shellSkinVars("novel", "forge") as Record<string, string>;
const paperVars = shellSkinVars("novel", "paper") as Record<string, string>;
check(forgeVars["--base"] !== paperVars["--base"], "Paper should be visually distinct from Forge");
check(paperVars["--signal-glow"] === "none", "Paper should suppress sci-fi signal glows");

const channel = (value: number) => {
  const normalized = value / 255;
  return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
};
const luminance = (hex: string) => {
  const value = Number.parseInt(hex.slice(1), 16);
  return 0.2126 * channel((value >> 16) & 255) + 0.7152 * channel((value >> 8) & 255) + 0.0722 * channel(value & 255);
};
const contrast = (a: string, b: string) => {
  const [bright, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (bright + 0.05) / (dark + 0.05);
};
check(contrast(paperVars["--txt"], paperVars["--base"]) >= 4.5, "Paper body text should meet WCAG AA contrast");
check(contrast(paperVars["--accent"], paperVars["--panel"]) >= 3, "Paper novel accent should remain legible on controls");

let mounts = 0;
let unmounts = 0;
function StatefulProbe() {
  const activeSkin = useSkin();
  useEffect(() => {
    mounts += 1;
    return () => { unmounts += 1; };
  }, []);
  return <div data-probe="stateful" data-active-skin={activeSkin}>draft state</div>;
}

const api = {
  listProjects: async () => [],
  getAdapt: async () => ({ mode: "Structure", stage: "draft", health: "healthy", override: "", description: "" }),
} as never;
const platform = {} as never;
const renderShell = (skin: SkinId) => (
  <StudioProvider services={{ api, platform }} writingMode="novel">
    <WorkspaceShell
      skin={skin}
      layout="focus"
      showConsole={false}
      centerSlot={<StatefulProbe />}
    />
  </StudioProvider>
);

let renderer!: ReactTestRenderer;
act(() => { renderer = create(renderShell("forge")); });
let shell = renderer.root.findByProps({ className: "lf-shell" });
check(shell.props["data-skin"] === "forge", "WorkspaceShell should expose the selected skin semantically");
check(shell.props.style["--base"] === forgeVars["--base"], "Forge variables should apply synchronously on the shell");
act(() => { renderer.update(renderShell("paper")); });
shell = renderer.root.findByProps({ className: "lf-shell" });
check(shell.props["data-skin"] === "paper", "WorkspaceShell should update data-skin immediately");
check(shell.props.style["--base"] === paperVars["--base"], "Paper variables should apply immediately");
check(renderer.root.findByProps({ "data-probe": "stateful" }).props["data-active-skin"] === "paper", "portal/panel descendants should receive the active Skin context");
check(mounts === 1 && unmounts === 0, "switching skins must not remount the writer's workspace");
act(() => { renderer.unmount(); });
check(unmounts === 1, "stateful skin test probe should clean up normally");

console.log(`${assertions} skin assertions passed.`);
