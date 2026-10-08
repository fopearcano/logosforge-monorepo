import { createContext, useContext, type ReactNode } from "react";
import type { SkinId } from "./shellVars";

const SkinContext = createContext<SkinId>("forge");

export function SkinProvider({ skin, children }: { skin: SkinId; children: ReactNode }) {
  return <SkinContext.Provider value={skin}>{children}</SkinContext.Provider>;
}

/** Active workspace Skin; defaults to Forge for standalone panel previews. */
export function useSkin(): SkinId {
  return useContext(SkinContext);
}
