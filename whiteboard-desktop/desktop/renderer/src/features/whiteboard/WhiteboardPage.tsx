/** Composes the whiteboard: writing-mode selector + load/save + editor + Logos,
 *  plus the Screenplay Preview / Settings / scale / export toolbar. */

import type { Editor } from '@tiptap/react';
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { PromptDialog } from '../../components/PromptDialog';
import { Popover } from '../../components/Popover';
import { deriveOutline } from '../outline/deriveOutline';
import type { OutlineItem } from '../outline/types';
import { EditorSettingsPopover } from '../editorTools/EditorSettingsPopover';
import { editorToolsAttrs, editorToolsVars } from '../editorTools/editorToolsSurface';
import { useFolding } from '../editorTools/folding/useFolding';
import { useEditorTools } from '../editorTools/useEditorTools';
import { filesAvailable, onMenuFile } from '../files/fileApi';
import { windowTitle } from '../files/fileState';
import { EXPORT_FORMATS, IMPORT_FORMATS } from '../files/importExportFormats';
import { useFileActions } from '../files/useFileActions';
import { useImportExport } from '../files/useImportExport';
import { setDocumentMenuApi } from '../../state/documentMenu';
import { LittleBoyProvider } from '../littleboy/LittleBoyProvider';
import { PreviewView } from '../screenplay/PreviewView';
import { printScreenplayPdf } from '../screenplay/printScreenplay';
import { toFountainBlocks } from '../screenplay/screenplayExport';
import type { FountainType } from '../screenplay/fountainTypes';
import { paginateScreenplay } from '../screenplay/screenplayPaginate';
import { screenplayLabel } from '../screenplay/screenplayClassifier';
import { useWritingModes } from '../writingModes/useWritingModes';
import { WritingModeSelector } from '../writingModes/WritingModeSelector';
import { surfaceDataAttrs } from './documentSettings';
import { modeBehavior } from './modes';
import { ProseToolbar } from './ProseToolbar';
import { ScreenplayToolbar } from './ScreenplayToolbar';
import { StoryMap } from './StoryMap';
import type { SaveStatus, WhiteboardBlock } from './types';
import { useDocumentSettings } from './useDocumentSettings';
import { useEditorScale } from './useEditorScale';
import { useWhiteboardDocument } from './useWhiteboardDocument';
import { blocksToDoc, WhiteboardEditor } from './WhiteboardEditor';
import { CommentsLayer } from '../comments/CommentsLayer';
import { findOrphanIds, reconcileMarks } from '../comments/commentsAnchor';
import { useResolvedHidden } from '../comments/commentsPanelStore';
import { useComments } from '../comments/useComments';

// Backend autosave/session indicator — deliberately labelled "Draft …" so it is
// never confused with an explicit File → Save (see the file-state chip).
const DRAFT_LABEL: Record<SaveStatus, string> = {
  idle: '',
  saving: 'Draft saving…',
  saved: 'Draft saved',
  error: 'Draft error',
};

interface Props {
  baseUrl: string;
  ready: boolean;
  onOutlineChange?: (items: OutlineItem[]) => void;
  /** Notifies the shell of the current writing mode (for outline defaults). */
  onModeChange?: (mode: string) => void;
  /** Notifies the shell of the current project name + unsaved state (title bar). */
  onTitleChange?: (name: string, dirty: boolean) => void;
}

export function WhiteboardPage({
  baseUrl,
  ready,
  onOutlineChange,
  onModeChange,
  onTitleChange,
}: Props) {
  const {
    doc,
    docList,
    loading,
    loadError,
    saveStatus,
    onChangeBlocks,
    setMode,
    selectDocument,
    newDocument: createNewDoc,
    deleteDocument: deleteDoc,
    renameDocument,
  } = useWhiteboardDocument({ baseUrl, ready });
  const { modes, defaultMode } = useWritingModes({ baseUrl, ready });
  const [editor, setEditor] = useState<Editor | null>(null);
  const [element, setElement] = useState<FountainType | null>(null);
  const [preview, setPreview] = useState(false);
  const [liveBlocks, setLiveBlocks] = useState<WhiteboardBlock[]>([]);
  const commentsApi = useComments(baseUrl, ready);
  const hideResolved = useResolvedHidden();
  const [activeCommentId, setActiveCommentId] = useState<string | null>(null);

  const settingsApi = useDocumentSettings();
  const { scale, apply: applyScale } = useEditorScale();

  // Optional Nerd Mode editor aids (all default off → clean by default).
  const editorToolsApi = useEditorTools();
  const editorTools = editorToolsApi.tools;
  const toggleTool = editorToolsApi.toggle;
  const resetTools = editorToolsApi.reset;
  const { folds, toggleFold, clearFolds } = useFolding();
  const resetEditorView = useCallback(() => {
    resetTools();
    clearFolds();
  }, [resetTools, clearFolds]);

  const onOutlineRef = useRef(onOutlineChange);
  onOutlineRef.current = onOutlineChange;
  const onModeChangeRef = useRef(onModeChange);
  onModeChangeRef.current = onModeChange;
  const onTitleChangeRef = useRef(onTitleChange);
  onTitleChangeRef.current = onTitleChange;
  const lastDocIdRef = useRef<string | null>(null);
  const previewRef = useRef(preview);
  previewRef.current = preview;

  const mode = doc?.mode ?? defaultMode;
  const isScreenplay = mode === 'screenplay';
  const showPreview = isScreenplay && preview;

  // The Mode dropdown PERMANENTLY converts THIS document's format (it is not
  // navigation — switching documents is the title menu). It's easy to nudge by
  // accident and the change is silent + sticky, so confirm when the document
  // already has text. (Empty/new docs change freely — you're just picking a mode.)
  // The mode a confirm dialog is currently asking about (null = no dialog). A
  // non-blocking, theme-styled dialog replaces window.confirm, which froze the
  // renderer synchronously.
  const [pendingMode, setPendingMode] = useState<string | null>(null);
  // Document-menu affordances (in-app dialogs, not window.prompt/confirm which are
  // unreliable in the packaged Electron app).
  const [renameOpen, setRenameOpen] = useState(false);
  const [docToDelete, setDocToDelete] = useState<string | null>(null);

  const requestModeChange = useCallback(
    (next: string) => {
      if (next === mode) return;
      const hasText = liveBlocks.some((b) => (b.text ?? '').trim().length > 0);
      // Empty/new docs switch freely; a doc with text confirms first — the reformat
      // is silent, sticky, and easy to trigger by accident.
      if (hasText) {
        setPendingMode(next);
        return;
      }
      setMode(next);
    },
    [mode, liveBlocks, setMode],
  );
  const pendingModeLabel = pendingMode
    ? (modes.find((m) => m.id === pendingMode)?.label ?? pendingMode)
    : '';

  // Story-map nodes derive from the same outline the panel uses — live blocks,
  // or the loaded doc before the first edit — gated by the active mode.
  const outlineItems = useMemo(
    () => deriveOutline(liveBlocks.length ? liveBlocks : (doc?.blocks ?? []), mode),
    [liveBlocks, doc, mode],
  );
  const commentMarks = useMemo(
    () =>
      reconcileMarks(
        hideResolved ? commentsApi.comments.filter((c) => !c.resolved) : commentsApi.comments,
        liveBlocks.map((b) => b.text ?? ''),
      ),
    [commentsApi.comments, liveBlocks, hideResolved],
  );
  // A comment must not outlive its anchor: when an edit deletes the block (or the
  // exact text) a comment is pinned to, the quote is gone from the whole doc —
  // delete the comment. Debounced past the autosave so it fires only after edits
  // settle, and guarded on a non-empty doc (findOrphanIds returns [] for no blocks)
  // so a load/doc-switch transient can never wipe live comments.
  const removeComment = commentsApi.remove;
  useEffect(() => {
    if (!liveBlocks.length || !commentsApi.comments.length) return undefined;
    const orphans = findOrphanIds(commentsApi.comments, liveBlocks.map((b) => b.text ?? ''));
    if (!orphans.length) return undefined;
    const timer = setTimeout(() => {
      orphans.forEach((id) => void removeComment(id));
    }, 1200);
    return () => clearTimeout(timer);
  }, [liveBlocks, commentsApi.comments, removeComment]);
  // Scroll the editor to a block (mirrors the shell's scrollToBlock; relies on
  // the `.wb-editor` direct-child-per-block invariant).
  const scrollToBlock = useCallback((blockIndex: number) => {
    const editorEl = document.querySelector('.wb-editor');
    const child = editorEl?.children[blockIndex] as HTMLElement | undefined;
    child?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, []);

  // Desktop file management (New/Open/Save/Save As) — backend autosave keeps the
  // session; these write user-chosen files. Loading a file replaces the editor
  // content (which re-autosaves), so the session copy stays in sync.
  const editorRef = useRef(editor);
  editorRef.current = editor;
  const liveBlocksRef = useRef(liveBlocks);
  liveBlocksRef.current = liveBlocks;
  const loadBlocks = useCallback((blocks: WhiteboardBlock[]) => {
    editorRef.current?.commands.setContent(blocksToDoc(blocks), true);
  }, []);
  // "New" creates a fresh DOCUMENT (blank manuscript + its own empty outline &
  // comments), same as the title-menu "New document" — not just a blank editor,
  // which would leave this document's outline orphaned against empty prose.
  const fileDoc = useFileActions({
    getBlocks: () => liveBlocksRef.current,
    loadBlocks,
    mode,
    onNewDocument: () => createNewDoc(),
  });
  const markFileDirty = fileDoc.markDirty;

  // Import / Export (extends file management; never alters Open/Save semantics).
  const importExport = useImportExport({
    baseUrl,
    getBlocks: () => liveBlocksRef.current,
    getMode: () => doc?.mode ?? defaultMode,
    getTitle: () => doc?.title ?? 'Untitled',
    getFileLabel: () => fileDoc.fileName,
    getSettings: () => settingsApi.settings,
    getComments: () =>
      commentsApi.comments.map((c) => ({
        quote: c.quote,
        body: c.body,
        resolved: c.resolved,
        blockIndex: c.anchor.block_index,
        createdAt: c.created_at,
      })),
    applySettings: settingsApi.replace,
    loadBlocks,
    setMode,
    markDirty: markFileDirty,
    confirmProceedPastUnsavedChanges: fileDoc.confirmProceedPastUnsavedChanges,
  });

  // Expose the document actions to the App-shell title menu (the dropdown under
  // the project name). Ref-backed so we register once but always call the latest.
  const fileDocRef = useRef(fileDoc);
  fileDocRef.current = fileDoc;
  const importExportRef = useRef(importExport);
  importExportRef.current = importExport;
  // Export PDF: paginated print for screenplays, plain print for prose modes.
  const printRef = useRef<() => void>(() => window.print());
  printRef.current = () => {
    if ((doc?.mode ?? defaultMode) === 'screenplay') {
      printScreenplayPdf(toFountainBlocks(liveBlocksRef.current));
    } else {
      window.print();
    }
  };
  useEffect(() => {
    setDocumentMenuApi({
      documents: docList,
      currentDocId: doc?.id ?? '',
      selectDocument,
      createDocument: () => createNewDoc(),
      deleteDocument: deleteDoc,
      renameCurrent: renameDocument,
      newDocument: () => fileDocRef.current.newDocument(),
      openDocument: () => fileDocRef.current.openDocument(),
      saveDocument: () => fileDocRef.current.saveDocument(),
      saveDocumentAs: () => fileDocRef.current.saveDocumentAs(),
      exportFountain: () => importExportRef.current.runExport('fountain'),
      printDocument: () => printRef.current(),
      hasFileBridge: filesAvailable(),
    });
  }, [docList, doc?.id, selectDocument, createNewDoc, deleteDoc, renameDocument]);

  // Clear the menu registration only on unmount (not on every list/id change).
  useEffect(() => () => setDocumentMenuApi(null), []);

  // The native File → Export → "Export as PDF" routes here (the data-export handler
  // ignores 'pdf'); PDF is the print path, not a file serializer.
  useEffect(() => onMenuFile((a) => { if (a === 'export:pdf') printRef.current(); }), []);

  // Autosave + recompute the (client-derived) outline + live snapshot on edit.
  const handleBlocks = useCallback(
    (blocks: WhiteboardBlock[]) => {
      markFileDirty();
      setLiveBlocks(blocks);
      onChangeBlocks(blocks);
      onOutlineRef.current?.(deriveOutline(blocks, doc?.mode ?? 'novel'));
    },
    [onChangeBlocks, doc?.mode, markFileDirty],
  );

  // The project name is the document title (documents auto-save to the app; there
  // is no separate on-disk file to name it after).
  const projectName = doc?.title || 'Untitled';

  // Reflect the project name + a transient "unsaved" marker (the backend autosave
  // in flight / failed) in BOTH the OS window title and the in-app title bar.
  useEffect(() => {
    const unsaved = saveStatus === 'saving' || saveStatus === 'error';
    document.title = windowTitle(projectName, unsaved);
    onTitleChangeRef.current?.(projectName, unsaved);
  }, [projectName, saveStatus]);

  // Re-derive the outline whenever the document loads or the mode changes; reset
  // the live snapshot only when a different document loads (a mode switch keeps
  // the current content, so re-derive from the live blocks, not doc.blocks).
  useEffect(() => {
    if (!doc) return;
    if (doc.id !== lastDocIdRef.current) {
      lastDocIdRef.current = doc.id;
      setLiveBlocks(doc.blocks);
      onOutlineRef.current?.(deriveOutline(doc.blocks, doc.mode));
    } else {
      onOutlineRef.current?.(deriveOutline(liveBlocksRef.current, doc.mode));
    }
  }, [doc]);

  // Surface the current writing mode to the shell (Outline mode-aware defaults).
  useEffect(() => {
    onModeChangeRef.current?.(mode);
  }, [mode]);

  // Leaving Screenplay mode exits Preview.
  useEffect(() => {
    if (!isScreenplay) setPreview(false);
  }, [isScreenplay]);

  // View scale (Ctrl/Cmd +/-/0), Preview toggle (Ctrl/Cmd+Shift+E), Esc exits.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && !e.altKey) {
        if (e.key === '=' || e.key === '+') {
          e.preventDefault();
          applyScale('bigger');
          return;
        }
        if (e.key === '-' || e.key === '_') {
          e.preventDefault();
          applyScale('smaller');
          return;
        }
        if (e.key === '0') {
          e.preventDefault();
          applyScale('actual');
          return;
        }
      }
      if (isScreenplay && mod && e.shiftKey && !e.altKey && (e.key === 'E' || e.key === 'e')) {
        e.preventDefault();
        setPreview((p) => !p);
        return;
      }
      // Nerd Mode toggles (work in every mode). Cmd/Ctrl+K stays free for Logos.
      if (mod && e.shiftKey && !e.altKey && (e.key === 'F' || e.key === 'f')) {
        e.preventDefault();
        toggleTool('folding');
        return;
      }
      if (mod && e.shiftKey && !e.altKey && (e.key === 'H' || e.key === 'h')) {
        e.preventDefault();
        toggleTool('syntax');
        return;
      }
      if (mod && !e.shiftKey && !e.altKey && (e.key === 'l' || e.key === 'L')) {
        e.preventDefault();
        toggleTool('lineNumbers');
        return;
      }
      if (e.key === 'Escape' && previewRef.current) {
        const ae = document.activeElement as HTMLElement | null;
        if (ae && (ae.closest('.wb-popover') || /^(INPUT|SELECT|TEXTAREA)$/.test(ae.tagName))) return;
        setPreview(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isScreenplay, applyScale, toggleTool]);

  // Exact page count from the SAME paginator the PDF export uses, so the on-screen
  // figure matches the printed script. Recomputes only on a content change (memo).
  const pageCount = useMemo(
    () => (isScreenplay ? paginateScreenplay(toFountainBlocks(liveBlocks)).length : 0),
    [isScreenplay, liveBlocks],
  );

  const surfaceStyle = {
    '--measure': modeBehavior(mode).measure,
    '--wb-scale': String(scale),
    ...editorToolsVars(editorTools),
  } as CSSProperties;
  const surfaceAttrs = {
    'data-writing-mode': mode,
    ...(isScreenplay ? { 'data-screenplay': '', ...surfaceDataAttrs(settingsApi.settings) } : {}),
    ...editorToolsAttrs(editorTools),
  };

  return (
    <main className="whiteboard">
      <ConfirmDialog
        open={pendingMode !== null}
        title="Change writing mode?"
        message={
          pendingMode
            ? `“${doc?.title?.trim() || 'this document'}” will be reformatted as ${pendingModeLabel}. ` +
              'Your text stays — only the structure is re-read for the new format.'
            : ''
        }
        confirmLabel={`Reformat as ${pendingModeLabel}`}
        cancelLabel="Cancel"
        onConfirm={() => {
          if (pendingMode) setMode(pendingMode);
          setPendingMode(null);
        }}
        onCancel={() => setPendingMode(null)}
      />
      <PromptDialog
        open={renameOpen}
        title="Rename document"
        initialValue={doc?.title ?? ''}
        placeholder="Document title"
        confirmLabel="Rename"
        onConfirm={(name) => {
          renameDocument(name);
          setRenameOpen(false);
        }}
        onCancel={() => setRenameOpen(false)}
      />
      <ConfirmDialog
        open={docToDelete !== null}
        title="Delete document"
        message={`Delete “${docList.find((d) => d.id === docToDelete)?.title || 'Untitled'}”? This also removes its outline and story bible. This can’t be undone.`}
        confirmLabel="Delete"
        onConfirm={() => {
          if (docToDelete) deleteDoc(docToDelete);
          setDocToDelete(null);
        }}
        onCancel={() => setDocToDelete(null)}
      />
      <div className="wb-statusline">
        <div className="wb-statusline-left">
          <Popover label="File" title="File menu">
            {(close) => (
              <div className="wb-menu wb-menu-scroll">
                <button
                  type="button"
                  className="wb-menu-item wb-menu-strong"
                  onClick={() => {
                    createNewDoc();
                    close();
                  }}
                >
                  New Document
                </button>

                <div className="wb-menu-sep" role="separator" />
                <div className="wb-menu-label">Open Document</div>
                {docList.map((d) => (
                  <div key={d.id} className="wb-doc-row">
                    <button
                      type="button"
                      role="menuitemradio"
                      aria-checked={d.id === doc?.id}
                      className={`wb-menu-item wb-doc-item${d.id === doc?.id ? ' is-current' : ''}`}
                      onClick={() => {
                        selectDocument(d.id);
                        close();
                      }}
                    >
                      <span className="wb-doc-check" aria-hidden="true">{d.id === doc?.id ? '✓' : ''}</span>
                      <span className="wb-doc-name">{d.title || 'Untitled'}</span>
                      <span className="wb-doc-mode">{d.mode}</span>
                    </button>
                    <button
                      type="button"
                      className="wb-doc-del"
                      title={`Delete “${d.title || 'Untitled'}”`}
                      aria-label={`Delete ${d.title || 'Untitled'}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setDocToDelete(d.id);
                        close();
                      }}
                    >
                      ×
                    </button>
                  </div>
                ))}

                <div className="wb-menu-sep" role="separator" />
                <button
                  type="button"
                  className="wb-menu-item"
                  onClick={() => {
                    setRenameOpen(true);
                    close();
                  }}
                >
                  Rename current document…
                </button>

                <div className="wb-menu-sep" role="separator" />
                <div className="wb-menu-label">Import</div>
                {IMPORT_FORMATS.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className="wb-menu-item"
                    onClick={() => {
                      importExport.runImport(f.id);
                      close();
                    }}
                  >
                    {f.label}
                  </button>
                ))}

                <div className="wb-menu-sep" role="separator" />
                <div className="wb-menu-label">Export</div>
                {EXPORT_FORMATS.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className="wb-menu-item"
                    onClick={() => {
                      importExport.runExport(f.id);
                      close();
                    }}
                  >
                    {f.label}
                  </button>
                ))}
                <button
                  type="button"
                  className="wb-menu-item"
                  onClick={() => {
                    printRef.current();
                    close();
                  }}
                >
                  Export as PDF…
                </button>
              </div>
            )}
          </Popover>
          <WritingModeSelector modes={modes} value={mode} onChange={requestModeChange} disabled={!doc} />
          {isScreenplay && (
            <span className="sp-element" title="Inferred screenplay element">
              {screenplayLabel(element)}
            </span>
          )}
        </div>
        <div className="wb-statusline-right">
          {/* Backend autosave indicator — documents save automatically. */}
          <span className={`wb-draft wb-draft-${saveStatus}`}>{DRAFT_LABEL[saveStatus]}</span>
          <EditorSettingsPopover api={editorToolsApi} onReset={resetEditorView} />
        </div>
      </div>

      {isScreenplay && (
        <ScreenplayToolbar
          editor={editor}
          blocks={liveBlocks}
          settingsApi={settingsApi}
          preview={preview}
          onTogglePreview={() => setPreview((p) => !p)}
          scale={scale}
          onScale={applyScale}
          pageCount={pageCount}
        />
      )}
      {!isScreenplay && <ProseToolbar editor={editor} scale={scale} onScale={applyScale} />}

      <div
        className={`wb-surface${showPreview ? ' is-preview' : ''}`}
        style={surfaceStyle}
        {...surfaceAttrs}
        onMouseDown={(e) => {
          // Click anywhere on the (full-panel) sheet to start writing.
          if (!showPreview && e.target === e.currentTarget) {
            e.preventDefault();
            editor?.chain().focus('end').run();
          }
        }}
      >
        {doc ? (
          <>
            <WhiteboardEditor
              key={doc.id}
              initialBlocks={doc.blocks}
              mode={doc.mode}
              onChangeBlocks={handleBlocks}
              onEditorReady={setEditor}
              onElementChange={setElement}
              editorTools={editorTools}
              folds={folds}
              onToggleFold={toggleFold}
              commentMarks={commentMarks}
              activeCommentId={activeCommentId}
              onCommentClick={setActiveCommentId}
            />
            {showPreview && <PreviewView blocks={liveBlocks} settings={settingsApi.settings} />}
          </>
        ) : !ready ? (
          <p className="wb-hint">Waiting for backend…</p>
        ) : loading ? (
          <p className="wb-hint">Loading…</p>
        ) : loadError ? (
          <p className="wb-hint wb-error">Couldn’t load document: {loadError}</p>
        ) : null}
      </div>
      {!showPreview && <StoryMap items={outlineItems} onNavigate={scrollToBlock} />}
      {editor && doc && (
        <LittleBoyProvider
          editor={editor}
          mode={doc.mode}
          baseUrl={baseUrl}
          documentTitle={fileDoc.fileName}
          screenplayElement={element}
        />
      )}
      {editor && doc && (
        <CommentsLayer
          editor={editor}
          api={commentsApi}
          activeId={activeCommentId}
          setActiveId={setActiveCommentId}
        />
      )}

      {importExport.feedback && (
        <div
          className={`wb-toast wb-toast-${importExport.feedback.kind}`}
          role="status"
          onClick={importExport.clearFeedback}
          title="Dismiss"
        >
          {importExport.feedback.message}
        </div>
      )}
    </main>
  );
}
