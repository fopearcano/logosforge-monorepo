import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';

import { bridge, type BackendStatus } from './api/backend';
import { StatusBar } from './components/StatusBar';
import { onMenuView } from './features/files/fileApi';
import { OutlinePanel } from './features/outline/OutlinePanel';
import type { OutlineItem } from './features/outline/types';
import { PsykeWindow } from './features/psyke/PsykeWindow';
import { HelpDialog } from './features/help/HelpDialog';
import { SettingsDialog } from './features/settings/SettingsDialog';
import {
  toggleCommentsPanel,
  useCommentsPanelOpen,
} from './features/comments/commentsPanelStore';
import { DEFAULT_BASE_URL } from './features/whiteboard/whiteboardApi';
import { WhiteboardPage } from './features/whiteboard/WhiteboardPage';
import { getDocumentMenuApi, subscribeDocumentMenu } from './state/documentMenu';
import {
  getLittleBoyOpenState,
  subscribeLittleBoyOpenState,
  toggleBilly,
  toggleLogos,
} from './state/littleBoyControl';
import { useUiVisibility } from './state/uiVisibilityStore';
import { PREDEFINED_THEMES } from './styles/themes/predefinedThemes';
import { ThemeSelector } from './styles/themes/ThemeSelector';
import { useTheme } from './styles/themes/useTheme';
import logoUrl from './assets/logo.png';

function scrollToBlock(index: number) {
  const surface = document.querySelector('.wb-editor');
  const child = surface?.children[index] as HTMLElement | undefined;
  child?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function currentSelectionText(): string {
  return window.getSelection()?.toString().trim() ?? '';
}

// --- outline panel width (draggable divider, persisted) ---------------------
const OUTLINE_W_KEY = 'lf-outline-width';
const OUTLINE_W_MIN = 220;
const OUTLINE_W_MAX = 620;
const OUTLINE_W_DEFAULT = 300;

function loadOutlineWidth(): number {
  try {
    const v = Number(localStorage.getItem(OUTLINE_W_KEY));
    if (Number.isFinite(v) && v >= OUTLINE_W_MIN && v <= OUTLINE_W_MAX) return v;
  } catch {
    /* ignore */
  }
  return OUTLINE_W_DEFAULT;
}

const clampOutlineWidth = (w: number) => Math.min(OUTLINE_W_MAX, Math.max(OUTLINE_W_MIN, w));

export function App() {
  const ui = useUiVisibility();
  const { themeId, setThemeId } = useTheme();
  const [status, setStatus] = useState<BackendStatus>({
    state: 'connecting',
    baseUrl: '',
    managed: false,
  });
  const [focusHint, setFocusHint] = useState(false);
  const [outlineItems, setOutlineItems] = useState<OutlineItem[]>([]);
  // The writing mode is owned by the document (WhiteboardPage); lift it here so
  // the Outline panel can apply mode-aware defaults to the manual outliner.
  const [docMode, setDocMode] = useState('novel');
  // Project name shown in the title bar — lifted from the document (WhiteboardPage)
  // so it updates live as projects load and files are saved.
  const [project, setProject] = useState<{ name: string; dirty: boolean }>({
    name: 'Untitled',
    dirty: false,
  });
  const [psykeOpen, setPsykeOpen] = useState(false);
  const [psykeQuery, setPsykeQuery] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  // Editor ↔ outline hard-link channel: the manuscript block the caret is in, the
  // block texts (for binding + re-anchoring), and the "you are here" breadcrumb.
  const [editorCaret, setEditorCaret] = useState<number | null>(null);
  const [editorBlockTexts, setEditorBlockTexts] = useState<string[]>([]);
  const [editorBlockTextsDocId, setEditorBlockTextsDocId] = useState<string | null>(null);
  const [activePath, setActivePath] = useState<string[]>([]);
  // Draggable outline↔manuscript divider width (persisted).
  const [outlineWidth, setOutlineWidth] = useState<number>(loadOutlineWidth);
  const persistOutlineWidth = useCallback((w: number) => {
    try {
      localStorage.setItem(OUTLINE_W_KEY, String(w));
    } catch {
      /* ignore */
    }
  }, []);
  const setOutlineWidthPersist = useCallback(
    (w: number) => {
      const next = clampOutlineWidth(w);
      setOutlineWidth(next);
      persistOutlineWidth(next);
    },
    [persistOutlineWidth],
  );
  // Functional nudge so rapid keypresses accumulate off the latest width, not a
  // stale render's value. Persist inside the updater (an idempotent localStorage
  // write) so it commits the SAME value the updater returns.
  const nudgeOutlineWidth = useCallback(
    (delta: number) => {
      setOutlineWidth((w) => {
        const next = clampOutlineWidth(w + delta);
        persistOutlineWidth(next);
        return next;
      });
    },
    [persistOutlineWidth],
  );
  const startOutlineResize = useCallback(
    (e: ReactPointerEvent) => {
      e.preventDefault();
      // Capture the pointer to the resizer element so a mouse release OUTSIDE the
      // window (or focus loss mid-drag) still delivers pointerup → we always clean
      // up. Element-scoped listeners + a buttons===0 guard belt-and-suspenders it.
      const el = e.currentTarget as HTMLElement;
      const pointerId = e.pointerId;
      const startX = e.clientX;
      const startWidth = outlineWidth;
      let cur = startWidth;
      function end() {
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', end);
        el.removeEventListener('pointercancel', end);
        el.removeEventListener('lostpointercapture', end);
        try {
          el.releasePointerCapture(pointerId);
        } catch {
          /* already released */
        }
        document.body.classList.remove('is-col-resizing');
        persistOutlineWidth(cur);
      }
      function move(ev: PointerEvent) {
        if (ev.buttons === 0) {
          end();
          return;
        }
        cur = clampOutlineWidth(startWidth + (ev.clientX - startX));
        setOutlineWidth(cur);
      }
      try {
        el.setPointerCapture(pointerId);
      } catch {
        /* capture unsupported — window fallback still works via the listeners below */
      }
      document.body.classList.add('is-col-resizing');
      el.addEventListener('pointermove', move);
      el.addEventListener('pointerup', end);
      el.addEventListener('pointercancel', end);
      el.addEventListener('lostpointercapture', end);
    },
    [outlineWidth, persistOutlineWidth],
  );
  const resetOutlineWidth = useCallback(
    () => setOutlineWidthPersist(OUTLINE_W_DEFAULT),
    [setOutlineWidthPersist],
  );
  // Keyboard resize (the divider is a focusable separator): ← / → nudge, Home/End jump.
  const onOutlineResizerKey = useCallback(
    (e: ReactKeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        nudgeOutlineWidth(-16);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        nudgeOutlineWidth(16);
      } else if (e.key === 'Home') {
        e.preventDefault();
        setOutlineWidthPersist(OUTLINE_W_MIN);
      } else if (e.key === 'End') {
        e.preventDefault();
        setOutlineWidthPersist(OUTLINE_W_MAX);
      }
    },
    [nudgeOutlineWidth, setOutlineWidthPersist],
  );
  const commentsPanelOpen = useCommentsPanelOpen();
  // Live open-state of the LittleBoy agents (Billy chat + Logos), published by
  // LittleBoyProvider — drives the title-bar toggle buttons' active state.
  const littleBoy = useSyncExternalStore(subscribeLittleBoyOpenState, getLittleBoyOpenState);
  // Project menu (the dropdown under the title), fed by WhiteboardPage.
  const docMenu = useSyncExternalStore(subscribeDocumentMenu, getDocumentMenuApi);
  const [titleMenuOpen, setTitleMenuOpen] = useState(false);
  const titleWrapRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!titleMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (titleWrapRef.current && !titleWrapRef.current.contains(e.target as Node)) setTitleMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation(); // close the menu without also restoring hidden panels
        setTitleMenuOpen(false);
      }
    };
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey, true);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey, true);
    };
  }, [titleMenuOpen]);

  // Briefly show "press Esc to exit" when entering Focus Mode (no permanent UI).
  useEffect(() => {
    if (!ui.focusModeActive) {
      setFocusHint(false);
      return;
    }
    setFocusHint(true);
    const t = setTimeout(() => setFocusHint(false), 2200);
    return () => clearTimeout(t);
  }, [ui.focusModeActive]);

  const toggleFocus = useCallback(() => {
    if (ui.focusModeActive) {
      ui.exitFocusMode();
    } else {
      setPsykeOpen(false); // entering: drop floating chrome
      ui.enterFocusMode();
    }
  }, [ui]);

  const cycleTheme = useCallback(() => {
    const i = PREDEFINED_THEMES.findIndex((t) => t.id === themeId);
    setThemeId(PREDEFINED_THEMES[(i + 1) % PREDEFINED_THEMES.length].id);
  }, [themeId, setThemeId]);

  const togglePsyke = useCallback(
    () =>
      setPsykeOpen((o) => {
        if (o) return false;
        setPsykeQuery(currentSelectionText());
        return true;
      }),
    [],
  );
  const openPsyke = useCallback(() => {
    setPsykeQuery(currentSelectionText());
    setPsykeOpen(true);
  }, []);

  // Hold latest handlers so the menu/keyboard listeners subscribe once.
  const actionsRef = useRef({
    toggleOutline: ui.toggleOutline,
    toggleTopPanel: ui.toggleTopPanel,
    toggleStoryMap: ui.toggleStoryMap,
    toggleFocus,
    cycleTheme,
    togglePsyke,
    handleEscape: ui.handleEscape,
  });
  actionsRef.current = {
    toggleOutline: ui.toggleOutline,
    toggleTopPanel: ui.toggleTopPanel,
    toggleStoryMap: ui.toggleStoryMap,
    toggleFocus,
    cycleTheme,
    togglePsyke,
    handleEscape: ui.handleEscape,
  };
  const psykeOpenRef = useRef(psykeOpen);
  psykeOpenRef.current = psykeOpen;

  useEffect(() => {
    let active = true;
    bridge.getBackendStatus().then((s) => {
      if (active) setStatus(s);
    });
    const unsubscribe = bridge.onBackendStatus((s) => setStatus(s));
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  // Native View-menu actions (mouse clicks). Matching shortcuts are handled below.
  useEffect(
    () =>
      onMenuView((action) => {
        const a = actionsRef.current;
        if (action === 'toggleTopPanel') a.toggleTopPanel();
        else if (action === 'toggleOutline') a.toggleOutline();
        else if (action === 'togglePsyke') a.togglePsyke();
        else if (action === 'toggleStoryMap') a.toggleStoryMap();
        else if (action === 'focusMode') a.toggleFocus();
        else if (action === 'toggleTheme') a.cycleTheme();
        else if (action === 'toggleComments') toggleCommentsPanel();
      }),
    [],
  );

  // Global view shortcuts + ESC restore. (Cmd/Ctrl+K stays Logos; never bound here.)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const a = actionsRef.current;
      if (e.key === 'Escape') {
        const ae = document.activeElement as HTMLElement | null;
        // Let a focused transient (popover/menu/PSYKE/LittleBoy/input) handle ESC
        // first. LittleBoy (Billy/Logos) closes via its own capture-phase handler.
        if (
          ae &&
          (ae.closest('.wb-popover') ||
            ae.closest('.psyke-window') ||
            ae.closest('.littleboy-box') ||
            /^(INPUT|SELECT|TEXTAREA)$/.test(ae.tagName))
        ) {
          return;
        }
        if (psykeOpenRef.current) {
          e.preventDefault();
          setPsykeOpen(false); // close the PSYKE window (a transient) first
          return;
        }
        if (a.handleEscape()) e.preventDefault(); // restore hidden panels / exit focus
        return;
      }
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || !e.shiftKey || e.altKey) return;
      if (e.code === 'KeyO') {
        e.preventDefault();
        a.toggleOutline();
      } else if (e.code === 'KeyP') {
        e.preventDefault();
        a.togglePsyke();
      } else if (e.code === 'KeyT') {
        e.preventDefault();
        a.toggleTopPanel();
      } else if (e.code === 'KeyM') {
        e.preventDefault();
        a.toggleStoryMap();
      } else if (e.code === 'KeyD') {
        e.preventDefault();
        a.toggleFocus();
      } else if (e.code === 'KeyC') {
        e.preventDefault();
        toggleCommentsPanel();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const baseUrl = status.baseUrl || DEFAULT_BASE_URL;
  const ready = status.state === 'connected';
  const appClass = `app${ui.topPanelVisible ? '' : ' is-top-hidden'}${ui.storyMapVisible ? '' : ' is-map-hidden'}${ui.focusModeActive ? ' is-focus' : ''}`;

  return (
    <div className={appClass}>
      <header className="titlebar">
        <img className="app-logo" src={logoUrl} alt="LogosForge" draggable={false} />
        <button
          type="button"
          className={`icon-toggle${ui.outlineVisible ? ' is-active' : ''}`}
          onClick={ui.toggleOutline}
          aria-pressed={ui.outlineVisible}
          title="Toggle Outline (Ctrl/Cmd+Shift+O)"
        >
          ☰
        </button>
        <div className="app-title-wrap" ref={titleWrapRef}>
          <button
            type="button"
            className={`app-title${project.dirty ? ' is-dirty' : ''}${titleMenuOpen ? ' is-open' : ''}`}
            onClick={() => setTitleMenuOpen((o) => !o)}
            aria-haspopup="menu"
            aria-expanded={titleMenuOpen}
            title={project.dirty ? `${project.name} — unsaved changes` : project.name}
          >
            {project.name}
          </button>
          {titleMenuOpen && docMenu && (
            <div className="app-title-menu wb-menu wb-menu-scroll" role="menu">
              <div className="wb-menu-label">Documents</div>
              {docMenu.documents.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={d.id === docMenu.currentDocId}
                  className={`wb-menu-item wb-doc-item${d.id === docMenu.currentDocId ? ' is-current' : ''}`}
                  onClick={() => {
                    setTitleMenuOpen(false);
                    docMenu.selectDocument(d.id);
                  }}
                >
                  <span className="wb-doc-check" aria-hidden="true">
                    {d.id === docMenu.currentDocId ? '✓' : ''}
                  </span>
                  <span className="wb-doc-name">{d.title || 'Untitled'}</span>
                  <span className="wb-doc-mode">{d.mode}</span>
                </button>
              ))}
              <button
                type="button"
                role="menuitem"
                className="wb-menu-item wb-menu-strong"
                onClick={() => {
                  setTitleMenuOpen(false);
                  docMenu.createDocument();
                }}
              >
                + New document
              </button>

              <div className="wb-menu-sep" role="separator" />
              <button
                type="button"
                role="menuitem"
                className="wb-menu-item"
                onClick={() => {
                  setTitleMenuOpen(false);
                  docMenu.exportFountain();
                }}
              >
                Export Fountain
              </button>
              <button
                type="button"
                role="menuitem"
                className="wb-menu-item"
                onClick={() => {
                  setTitleMenuOpen(false);
                  docMenu.printDocument();
                }}
              >
                Export PDF…
              </button>
            </div>
          )}
        </div>
        <div className="titlebar-right">
          <button
            type="button"
            className="icon-toggle"
            onClick={toggleFocus}
            title="Focus Mode (Ctrl/Cmd+Shift+D · Esc restores)"
            aria-label="Enter Focus Mode"
          >
            ◌
          </button>
          <button
            type="button"
            className="icon-toggle"
            onClick={ui.toggleTopPanel}
            title="Hide top panel (Ctrl/Cmd+Shift+T · Esc restores)"
            aria-label="Hide top panel"
          >
            ▲
          </button>
          <ThemeSelector />
          <button
            type="button"
            className={`icon-toggle${helpOpen ? ' is-active' : ''}`}
            onClick={() => setHelpOpen(true)}
            title="Quick Start & hotkeys"
            aria-label="Quick Start and hotkeys"
          >
            ?
          </button>
          <button
            type="button"
            className={`icon-toggle${settingsOpen ? ' is-active' : ''}`}
            onClick={() => setSettingsOpen(true)}
            title="AI provider settings"
            aria-label="AI provider settings"
          >
            ⚙
          </button>
          <button
            type="button"
            className={`psyke-toggle${littleBoy.billyOpen ? ' is-active' : ''}`}
            onClick={toggleBilly}
            aria-pressed={littleBoy.billyOpen}
            title="Toggle LittleBoy chat (Ctrl/Cmd+Shift+B)"
          >
            LittleBoy
          </button>
          <button
            type="button"
            className={`psyke-toggle${littleBoy.logosOpen ? ' is-active' : ''}`}
            onClick={toggleLogos}
            aria-pressed={littleBoy.logosOpen}
            title="Toggle Logos (Ctrl/Cmd+Shift+L)"
          >
            Logos
          </button>
          <button
            type="button"
            className={`psyke-toggle${commentsPanelOpen ? ' is-active' : ''}`}
            onClick={toggleCommentsPanel}
            aria-pressed={commentsPanelOpen}
            title="Toggle Comments (Ctrl/Cmd+Shift+C)"
          >
            Comments
          </button>
          {ui.psykeButtonVisible && (
            <button
              type="button"
              className={`psyke-toggle${psykeOpen ? ' is-active' : ''}`}
              onClick={() => (psykeOpen ? setPsykeOpen(false) : openPsyke())}
              aria-pressed={psykeOpen}
              title="Toggle PSYKE (Ctrl/Cmd+Shift+P)"
            >
              PSYKE
            </button>
          )}
        </div>
      </header>
      <div className="workarea" style={{ '--outline-w': `${outlineWidth}px` } as CSSProperties}>
        {ui.outlineVisible && (
          <OutlinePanel
            derivedItems={outlineItems}
            onNavigate={(item) => scrollToBlock(item.blockIndex)}
            baseUrl={baseUrl}
            ready={ready}
            mode={docMode}
            caretBlockIndex={editorCaret}
            blockTexts={editorBlockTexts}
            blockTextsDocId={editorBlockTextsDocId}
            onNavigateBlock={scrollToBlock}
            onActivePathChange={setActivePath}
          />
        )}
        {ui.outlineVisible && (
          <div
            className="workarea-resizer"
            role="separator"
            aria-orientation="vertical"
            tabIndex={0}
            aria-label="Resize outline panel"
            aria-valuenow={outlineWidth}
            aria-valuemin={OUTLINE_W_MIN}
            aria-valuemax={OUTLINE_W_MAX}
            title="Drag or ← → to resize · double-click to reset"
            onPointerDown={startOutlineResize}
            onDoubleClick={resetOutlineWidth}
            onKeyDown={onOutlineResizerKey}
          />
        )}
        <WhiteboardPage
          baseUrl={baseUrl}
          ready={ready}
          onOutlineChange={setOutlineItems}
          onModeChange={setDocMode}
          onTitleChange={(name, dirty) => setProject({ name, dirty })}
          locationPath={activePath}
          onEditorLocation={(caret, texts, docId) => {
            setEditorCaret(caret);
            setEditorBlockTexts(texts);
            setEditorBlockTextsDocId(docId);
          }}
        />
      </div>
      {psykeOpen && (
        <PsykeWindow baseUrl={baseUrl} initialQuery={psykeQuery} onClose={() => setPsykeOpen(false)} />
      )}
      <SettingsDialog open={settingsOpen} baseUrl={baseUrl} onClose={() => setSettingsOpen(false)} />
      <HelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
      {ui.statusBarVisible && <StatusBar status={status} />}
      {focusHint && <div className="focus-hint">Focus Mode — press Esc to exit</div>}
    </div>
  );
}
