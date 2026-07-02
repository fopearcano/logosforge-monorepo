/**
 * Central UI visibility state for the Whiteboard chrome (top panel, outline,
 * status bar, PSYKE button) + Focus Mode. ESC restores everything.
 *
 * Persisted: the panel visibility booleans. Session-only: Focus Mode (always
 * starts off) + the pre-focus snapshot.
 */

import { useCallback, useRef, useState } from 'react';

export interface VisibilitySnapshot {
  topPanelVisible: boolean;
  outlineVisible: boolean;
  statusBarVisible: boolean;
  psykeButtonVisible: boolean;
  storyMapVisible: boolean;
}

export interface UiVisibility extends VisibilitySnapshot {
  focusModeActive: boolean;
  toggleTopPanel: () => void;
  toggleOutline: () => void;
  toggleStatusBar: () => void;
  togglePsykeButton: () => void;
  toggleStoryMap: () => void;
  enterFocusMode: () => void;
  exitFocusMode: () => void;
  restoreStandardPanels: () => void;
  /** Restore hidden panels / exit Focus Mode. Returns true if it changed anything. */
  handleEscape: () => boolean;
}

const KEYS: Record<keyof VisibilitySnapshot, string> = {
  topPanelVisible: 'lf-vis-top',
  outlineVisible: 'lf-vis-outline',
  statusBarVisible: 'lf-vis-status',
  psykeButtonVisible: 'lf-vis-psyke',
  storyMapVisible: 'lf-vis-map',
};

function loadBool(key: string, def: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    if (v === '1') return true;
    if (v === '0') return false;
  } catch {
    /* ignore */
  }
  return def;
}
function saveBool(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? '1' : '0');
  } catch {
    /* ignore */
  }
}

export function useUiVisibility(): UiVisibility {
  const [topPanelVisible, setTop] = useState(() => loadBool(KEYS.topPanelVisible, true));
  const [outlineVisible, setOutline] = useState(() => loadBool(KEYS.outlineVisible, true));
  const [statusBarVisible, setStatus] = useState(() => loadBool(KEYS.statusBarVisible, true));
  const [psykeButtonVisible, setPsyke] = useState(() => loadBool(KEYS.psykeButtonVisible, true));
  const [storyMapVisible, setMap] = useState(() => loadBool(KEYS.storyMapVisible, true));
  const [focusModeActive, setFocus] = useState(false);
  const prevRef = useRef<VisibilitySnapshot | null>(null);

  // Latest values for the callbacks (which are stable / dependency-free).
  const latest = useRef<VisibilitySnapshot & { focus: boolean }>({
    topPanelVisible,
    outlineVisible,
    statusBarVisible,
    psykeButtonVisible,
    storyMapVisible,
    focus: focusModeActive,
  });
  latest.current = { topPanelVisible, outlineVisible, statusBarVisible, psykeButtonVisible, storyMapVisible, focus: focusModeActive };

  const putTop = useCallback((v: boolean) => {
    saveBool(KEYS.topPanelVisible, v);
    setTop(v);
  }, []);
  const putOutline = useCallback((v: boolean) => {
    saveBool(KEYS.outlineVisible, v);
    setOutline(v);
  }, []);
  const putStatus = useCallback((v: boolean) => {
    saveBool(KEYS.statusBarVisible, v);
    setStatus(v);
  }, []);
  const putPsyke = useCallback((v: boolean) => {
    saveBool(KEYS.psykeButtonVisible, v);
    setPsyke(v);
  }, []);
  const putMap = useCallback((v: boolean) => {
    saveBool(KEYS.storyMapVisible, v);
    setMap(v);
  }, []);

  const toggleTopPanel = useCallback(() => putTop(!latest.current.topPanelVisible), [putTop]);
  const toggleOutline = useCallback(() => putOutline(!latest.current.outlineVisible), [putOutline]);
  const toggleStatusBar = useCallback(() => putStatus(!latest.current.statusBarVisible), [putStatus]);
  const togglePsykeButton = useCallback(() => putPsyke(!latest.current.psykeButtonVisible), [putPsyke]);
  const toggleStoryMap = useCallback(() => putMap(!latest.current.storyMapVisible), [putMap]);

  const enterFocusMode = useCallback(() => {
    const s = latest.current;
    prevRef.current = {
      topPanelVisible: s.topPanelVisible,
      outlineVisible: s.outlineVisible,
      statusBarVisible: s.statusBarVisible,
      psykeButtonVisible: s.psykeButtonVisible,
      storyMapVisible: s.storyMapVisible,
    };
    setFocus(true);
  }, []);

  const exitFocusMode = useCallback(() => {
    setFocus(false);
    const prev = prevRef.current;
    if (prev) {
      putTop(prev.topPanelVisible);
      putOutline(prev.outlineVisible);
      putStatus(prev.statusBarVisible);
      putPsyke(prev.psykeButtonVisible);
      putMap(prev.storyMapVisible);
    }
  }, [putTop, putOutline, putStatus, putPsyke, putMap]);

  const restoreStandardPanels = useCallback(() => {
    setFocus(false);
    putTop(true);
    putOutline(true);
    putStatus(true);
    putPsyke(true);
    putMap(true);
  }, [putTop, putOutline, putStatus, putPsyke, putMap]);

  const handleEscape = useCallback((): boolean => {
    const s = latest.current;
    const anythingHidden =
      !s.topPanelVisible || !s.outlineVisible || !s.statusBarVisible || !s.psykeButtonVisible || !s.storyMapVisible;
    if (s.focus || anythingHidden) {
      restoreStandardPanels();
      return true;
    }
    return false;
  }, [restoreStandardPanels]);

  return {
    topPanelVisible,
    outlineVisible,
    statusBarVisible,
    psykeButtonVisible,
    storyMapVisible,
    focusModeActive,
    toggleTopPanel,
    toggleOutline,
    toggleStatusBar,
    togglePsykeButton,
    toggleStoryMap,
    enterFocusMode,
    exitFocusMode,
    restoreStandardPanels,
    handleEscape,
  };
}
