import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import type {
  ProjectDTO,
  ProjectSearchMatchDTO,
  PsykeConsoleCommandPlanDTO,
  PsykeConsoleSuggestionDTO,
} from "@logosforge/ui-contracts";
import {
  activateOmniboxItem,
  buildOmniboxItems,
  executeOmniboxPlan,
  firstEnabledOmniboxIndex,
  flattenOmniboxSections,
  moveOmniboxSelection,
  omniboxOptionDomId,
  searchOmniboxItems,
  StaleOmniboxPlanError,
  type CommandRegistry,
  type OmniboxItem,
  type OmniboxPanel,
  type OmniboxPlanOwner,
} from "../../commands";
import { PendingProjectSaveError, flushPendingProjectSaves } from "../../adapters/projectSaveCoordinator";
import { useSelection } from "../../adapters/selection";
import { useStudio, type StudioNavigationOptions } from "../../adapters/StudioProvider";
import { createLatestRequestGate } from "../../hooks/latestRequest";
import { ModalPortal } from "../common/ModalPortal";
import { useModalDialog } from "../common/useModalDialog";
import { usePanelHostDocument, usePanelHostWindow } from "../common/PanelHost";

const backdropStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 9999,
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "center",
  paddingTop: "10vh",
  background: "rgba(2,4,8,.62)",
  backdropFilter: "blur(3px)",
};

const dialogStyle: CSSProperties = {
  width: "min(760px, 94vw)",
  maxHeight: "80vh",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
  border: "1px solid var(--line-cy)",
  borderRadius: 5,
  background: "var(--raised)",
  color: "var(--txt)",
  boxShadow: "0 28px 90px rgba(0,0,0,.58)",
  fontFamily: "'JetBrains Mono', monospace",
};

const inputStyle: CSSProperties = {
  width: "100%",
  minHeight: 52,
  padding: "14px 18px",
  border: "none",
  borderBottom: "1px solid var(--line2)",
  outline: "none",
  background: "transparent",
  color: "var(--strong)",
  font: "inherit",
  fontSize: 14,
  letterSpacing: ".02em",
};

const optionStyle: CSSProperties = {
  width: "100%",
  minHeight: 42,
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  alignItems: "center",
  gap: 12,
  padding: "7px 12px",
  border: "none",
  borderRadius: 3,
  color: "var(--txt)",
  font: "inherit",
  textAlign: "left",
};

const actionButtonStyle: CSSProperties = {
  minHeight: 32,
  padding: "5px 13px",
  border: "1px solid var(--line2)",
  background: "var(--panel2)",
  color: "var(--txt)",
  font: "inherit",
  fontSize: 9,
  letterSpacing: ".1em",
  cursor: "pointer",
};

type ViewItem = {
  readonly key: string;
  readonly group: string;
  readonly label: string;
  readonly detail: string;
  readonly shortcut?: string;
  readonly disabled: boolean;
} & (
  | { readonly viewKind: "target"; readonly target: OmniboxItem }
  | { readonly viewKind: "plan"; readonly command: string }
  | { readonly viewKind: "suggestion"; readonly suggestion: PsykeConsoleSuggestionDTO }
);

interface ViewSection {
  readonly group: string;
  readonly items: readonly ViewItem[];
}

export interface StudioOmniboxProps {
  open: boolean;
  onClose(): void;
  registry: CommandRegistry;
  panels: readonly OmniboxPanel[];
  projects: readonly ProjectDTO[];
  recentProjectIds?: readonly number[];
  onNavigate(panelId: string, options?: StudioNavigationOptions): Promise<boolean>;
  onSelectProject(projectId: number): Promise<boolean>;
  onError?(error: unknown, label: string): void;
}

function errorMessage(prefix: string, error: unknown): string {
  return `${prefix} ${error instanceof Error ? error.message : String(error)}`;
}

function planOwnerMatches(
  owner: OmniboxPlanOwner | null,
  projectId: number | undefined,
  sceneId: number | null,
): boolean {
  return owner != null && owner.projectId === projectId && owner.sceneId === sceneId;
}

/** Shared desktop/browser project omnibox. All writes remain API/host-authoritative. */
export function StudioOmnibox({
  open,
  onClose,
  registry,
  panels,
  projects,
  recentProjectIds = [],
  onNavigate,
  onSelectProject,
  onError,
}: StudioOmniboxProps) {
  const { api, projectId } = useStudio();
  const ownerDocument = usePanelHostDocument();
  const ownerWindow = usePanelHostWindow();
  const { selection } = useSelection();
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const activatingRef = useRef(false);
  const executingRef = useRef(false);
  const planAbortRef = useRef<AbortController | null>(null);
  const suggestionAbortRef = useRef<AbortController | null>(null);
  const projectSearchAbortRef = useRef<AbortController | null>(null);
  const openRef = useRef(open);
  openRef.current = open;
  const identityRef = useRef({ projectId, sceneId: selection.sceneId });
  identityRef.current = { projectId, sceneId: selection.sceneId };
  const requests = useRef(createLatestRequestGate()).current;
  const idPrefix = `lf-studio-omnibox-${useId().replace(/:/g, "")}`;
  const listId = `${idPrefix}-results`;
  const descriptionId = `${idPrefix}-description`;
  const planTitleId = `${idPrefix}-plan-title`;
  const planDescriptionId = `${idPrefix}-plan-description`;
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [projectMatches, setProjectMatches] = useState<readonly ProjectSearchMatchDTO[]>([]);
  const [projectMatchesOwner, setProjectMatchesOwner] = useState<{ projectId: number; query: string } | null>(null);
  const [projectSearchLoading, setProjectSearchLoading] = useState(false);
  const [projectSearchError, setProjectSearchError] = useState("");
  const [suggestions, setSuggestions] = useState<readonly PsykeConsoleSuggestionDTO[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [actionError, setActionError] = useState("");
  const [activating, setActivating] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [plan, setPlan] = useState<PsykeConsoleCommandPlanDTO | null>(null);
  const [planOwner, setPlanOwner] = useState<OmniboxPlanOwner | null>(null);
  const [message, setMessage] = useState("");
  const planRef = useRef(plan);
  planRef.current = plan;

  const cancelPlan = useCallback((nextMessage = "Command preview cancelled.") => {
    const executionInFlight = executingRef.current;
    planAbortRef.current?.abort();
    planAbortRef.current = null;
    requests.invalidate("plan");
    setPlanning(false);
    if (!executionInFlight) setExecuting(false);
    setPlan(null);
    setPlanOwner(null);
    setActionError("");
    setMessage(nextMessage);
    ownerWindow?.requestAnimationFrame(() => inputRef.current?.focus());
  }, [ownerWindow, requests]);

  const closeNow = useCallback(() => {
    planAbortRef.current?.abort();
    planAbortRef.current = null;
    suggestionAbortRef.current?.abort();
    suggestionAbortRef.current = null;
    projectSearchAbortRef.current?.abort();
    projectSearchAbortRef.current = null;
    requests.invalidate("plan");
    requests.invalidate("suggestions");
    requests.invalidate("project-search");
    requests.invalidate("execute");
    setPlan(null);
    setPlanOwner(null);
    onClose();
  }, [onClose, requests]);

  const requestClose = useCallback(() => {
    if (activatingRef.current || executingRef.current) return;
    // Escape is captured by the modal before React's review-section handler.
    // Treat its first press as plan cancellation; a second press closes the
    // now-unplanned omnibox.
    if (planRef.current) {
      cancelPlan();
      return;
    }
    closeNow();
  }, [cancelPlan, closeNow]);

  useModalDialog({
    open,
    dialogRef,
    initialFocusRef: inputRef,
    onClose: requestClose,
    // Planning is read-only and abortable. A reviewed plan uses the first
    // Escape to cancel its preview; activation/execution remain locked.
    canClose: !activating && !executing,
  });

  useEffect(() => {
    if (!open) {
      planAbortRef.current?.abort();
      planAbortRef.current = null;
      suggestionAbortRef.current?.abort();
      suggestionAbortRef.current = null;
      projectSearchAbortRef.current?.abort();
      projectSearchAbortRef.current = null;
      requests.close();
      return;
    }
    requests.open();
    setQuery("");
    setSelectedIndex(-1);
    setSuggestions([]);
    setSuggestionsLoading(false);
    setSuggestionError("");
    setProjectMatches([]);
    setProjectMatchesOwner(null);
    setProjectSearchLoading(false);
    setProjectSearchError("");
    setActionError("");
    setMessage("");
    setPlan(null);
    setPlanOwner(null);
    setPlanning(false);
    setExecuting(false);
    activatingRef.current = false;
    executingRef.current = false;
    return () => {
      planAbortRef.current?.abort();
      planAbortRef.current = null;
      suggestionAbortRef.current?.abort();
      suggestionAbortRef.current = null;
      projectSearchAbortRef.current?.abort();
      projectSearchAbortRef.current = null;
      requests.close();
    };
  }, [open, requests]);

  useEffect(() => {
    if (!open || !planOwner) return;
    if (!planOwnerMatches(planOwner, projectId, selection.sceneId)) {
      cancelPlan("Command preview expired because the project context changed.");
    }
  }, [cancelPlan, open, planOwner, projectId, selection.sceneId]);

  const sourceItems = useMemo(() => buildOmniboxItems({
    commands: registry.list(),
    panels,
    projects,
    recentProjectIds,
    activeProjectId: projectId,
    projectMatches: projectMatchesOwner != null
      && projectMatchesOwner.projectId === projectId
      && projectMatchesOwner.query === query.trim()
      ? projectMatches
      : [],
  }), [panels, projectId, projectMatches, projectMatchesOwner, projects, query, recentProjectIds, registry]);

  const localSections = useMemo(
    () => searchOmniboxItems(sourceItems, query),
    [query, sourceItems],
  );

  const slashQuery = query.trim().startsWith("/");
  useEffect(() => {
    projectSearchAbortRef.current?.abort();
    projectSearchAbortRef.current = null;
    requests.invalidate("project-search");
    setProjectSearchLoading(false);
    setProjectSearchError("");
    const searchQuery = query.trim();
    if (!open || slashQuery || !searchQuery || projectId == null || plan != null || planning) return;
    const timer = ownerWindow?.setTimeout(() => {
      const token = requests.begin("project-search");
      const controller = new AbortController();
      projectSearchAbortRef.current = controller;
      setProjectSearchLoading(true);
      void api.searchProject(projectId, searchQuery, ["scene", "note", "psyke", "comment"], controller.signal).then(
        (response) => {
          if (!requests.isCurrent(token) || identityRef.current.projectId !== projectId) return;
          if (projectSearchAbortRef.current === controller) projectSearchAbortRef.current = null;
          setProjectMatches(response.matches);
          setProjectMatchesOwner({ projectId, query: searchQuery });
          setProjectSearchLoading(false);
        },
        (error) => {
          if (!requests.isCurrent(token) || identityRef.current.projectId !== projectId) return;
          if (projectSearchAbortRef.current === controller) projectSearchAbortRef.current = null;
          if (error instanceof Error && error.name === "AbortError") return;
          setProjectSearchLoading(false);
          setProjectSearchError(errorMessage("Project search failed.", error));
        },
      );
    }, 120);
    return () => {
      if (timer != null) ownerWindow?.clearTimeout(timer);
      projectSearchAbortRef.current?.abort();
      projectSearchAbortRef.current = null;
    };
  }, [api, open, ownerWindow, plan, planning, projectId, query, requests, slashQuery]);

  useEffect(() => {
    suggestionAbortRef.current?.abort();
    suggestionAbortRef.current = null;
    requests.invalidate("suggestions");
    setSuggestions([]);
    setSuggestionsLoading(false);
    setSuggestionError("");
    if (!open || !slashQuery || projectId == null || plan != null || planning) return;
    const command = query.trim();
    if (!command) return;
    const timer = ownerWindow?.setTimeout(() => {
      const token = requests.begin("suggestions");
      const controller = new AbortController();
      suggestionAbortRef.current = controller;
      setSuggestionsLoading(true);
      void api.getPsykeConsoleSuggestions(projectId, command, selection.sceneId, controller.signal).then(
        (next) => {
          if (!requests.isCurrent(token) || identityRef.current.projectId !== projectId) return;
          if (suggestionAbortRef.current === controller) suggestionAbortRef.current = null;
          setSuggestions(next);
          setSuggestionsLoading(false);
        },
        (error) => {
          if (!requests.isCurrent(token) || identityRef.current.projectId !== projectId) return;
          if (suggestionAbortRef.current === controller) suggestionAbortRef.current = null;
          if (error instanceof Error && error.name === "AbortError") return;
          setSuggestionsLoading(false);
          setSuggestionError(errorMessage("Command suggestions failed.", error));
        },
      );
    }, 120);
    return () => {
      if (timer != null) ownerWindow?.clearTimeout(timer);
      suggestionAbortRef.current?.abort();
      suggestionAbortRef.current = null;
    };
  }, [api, open, ownerWindow, plan, planning, projectId, query, requests, selection.sceneId, slashQuery]);

  const viewSections = useMemo<readonly ViewSection[]>(() => {
    if (slashQuery) {
      const command = query.trim();
      const items: ViewItem[] = [];
      if (command.length > 1) {
        items.push({
          key: `plan:${command}`,
          group: "Commands",
          label: `Preview ${command}`,
          detail: "Resolve the exact target and effects before anything runs",
          disabled: planning || executing,
          viewKind: "plan",
          command,
        });
      }
      for (const suggestion of suggestions) {
        if (suggestion.text === command) continue;
        items.push({
          key: `suggestion:${suggestion.category}:${suggestion.entry_id}:${suggestion.text}`,
          group: "Commands",
          label: suggestion.text,
          detail: suggestion.description || suggestion.category.replaceAll("_", " "),
          disabled: planning || executing,
          viewKind: "suggestion",
          suggestion,
        });
      }
      return items.length ? [{ group: "Commands", items }] : [];
    }
    return localSections.map((section) => ({
      group: section.group,
      items: section.items.map((target): ViewItem => ({
        key: target.key,
        group: target.group,
        label: target.label,
        detail: target.detail,
        shortcut: target.shortcut,
        disabled: target.disabled || activating,
        viewKind: "target",
        target,
      })),
    }));
  }, [activating, executing, localSections, planning, query, slashQuery, suggestions]);

  const flatItems = useMemo(() => viewSections.flatMap((section) => section.items), [viewSections]);
  useEffect(() => {
    setSelectedIndex((current) => {
      if (current >= 0 && current < flatItems.length && !flatItems[current]!.disabled) return current;
      return firstEnabledOmniboxIndex(flatItems);
    });
  }, [flatItems]);
  const activeItem = flatItems[selectedIndex];
  const activeOptionId = activeItem ? omniboxOptionDomId(idPrefix, activeItem.key) : undefined;
  useEffect(() => {
    if (!open || plan != null || !activeOptionId) return;
    ownerDocument?.getElementById(activeOptionId)?.scrollIntoView({ block: "nearest" });
  }, [activeOptionId, open, ownerDocument, plan]);

  const planCommand = useCallback((rawCommand: string) => {
    const command = rawCommand.trim();
    if (projectId == null) {
      setActionError("Open a project before previewing a command.");
      return;
    }
    if (!command.startsWith("/")) return;
    planAbortRef.current?.abort();
    const controller = new AbortController();
    planAbortRef.current = controller;
    const ownerIdentity = { projectId, sceneId: selection.sceneId };
    const token = requests.begin("plan");
    setPlan(null);
    setPlanOwner(null);
    setPlanning(true);
    setActionError("");
    setMessage("Planning command…");
    void api.planPsykeConsoleCommand(
      projectId,
      { command, active_scene_id: selection.sceneId },
      controller.signal,
    ).then(
      (nextPlan) => {
        if (!requests.isCurrent(token)
          || identityRef.current.projectId !== ownerIdentity.projectId
          || identityRef.current.sceneId !== ownerIdentity.sceneId) return;
        if (planAbortRef.current === controller) planAbortRef.current = null;
        setPlanning(false);
        setPlan(nextPlan);
        setPlanOwner({ ...ownerIdentity, planId: nextPlan.plan_id });
        setQuery(nextPlan.normalized_command);
        setMessage(nextPlan.requires_confirmation
          ? "Review the project change before confirming."
          : "Review the resolved navigation target.");
        ownerWindow?.requestAnimationFrame(() => confirmRef.current?.focus());
      },
      (error) => {
        if (!requests.isCurrent(token)) return;
        if (planAbortRef.current === controller) planAbortRef.current = null;
        if (error instanceof Error && error.name === "AbortError") return;
        setPlanning(false);
        setPlan(null);
        setPlanOwner(null);
        const detail = errorMessage("Command preview failed.", error);
        setActionError(detail);
        setMessage("");
        onError?.(error, command);
      },
    );
  }, [api, onError, ownerWindow, projectId, requests, selection.sceneId]);

  const activateTarget = useCallback(async (item: OmniboxItem) => {
    if (activatingRef.current || item.disabled) return;
    activatingRef.current = true;
    setActivating(true);
    setActionError("");
    setMessage(`Opening ${item.label}…`);
    try {
      const succeeded = await activateOmniboxItem(item, {
        flush: () => flushPendingProjectSaves({ commitActiveField: true }),
        registry,
        navigate: onNavigate,
        selectProject: onSelectProject,
      });
      if (!succeeded) {
        setActionError(`${item.label} was not opened because the current workspace could not complete the handoff.`);
        setMessage("");
        return;
      }
      closeNow();
    } catch (error) {
      const detail = errorMessage(`${item.label} was not opened.`, error);
      setActionError(detail);
      setMessage("");
      onError?.(error, item.label);
    } finally {
      activatingRef.current = false;
      setActivating(false);
    }
  }, [closeNow, onError, onNavigate, onSelectProject, registry]);

  const activateViewItem = useCallback((item: ViewItem) => {
    if (item.disabled) return;
    if (item.viewKind === "target") {
      void activateTarget(item.target);
      return;
    }
    if (item.viewKind === "plan") {
      planCommand(item.command);
      return;
    }
    const suggestion = item.suggestion;
    if (suggestion.entry_id > 0 && suggestion.category === "entity" && !suggestion.text.startsWith("/")) {
      const target = buildOmniboxItems({
        commands: [], panels: [], projects: [], recentProjectIds: [],
        projectMatches: [{
          kind: "psyke",
          id: suggestion.entry_id,
          title: suggestion.text,
          excerpt: suggestion.description,
        }],
      })[0];
      if (target) void activateTarget(target);
      return;
    }
    setQuery(suggestion.text.endsWith(" ") ? suggestion.text : `${suggestion.text} `);
    setSuggestions([]);
    setSelectedIndex(-1);
    setMessage("Complete the command, then preview its exact effect.");
    ownerWindow?.requestAnimationFrame(() => inputRef.current?.focus());
  }, [activateTarget, ownerWindow, planCommand]);

  const runPlan = useCallback(async () => {
    if (!plan || !planOwner || executingRef.current) return;
    const token = requests.begin("execute");
    executingRef.current = true;
    setExecuting(true);
    setActionError("");
    setMessage("Saving pending edits before command execution…");
    try {
      const result = await executeOmniboxPlan({
        plan,
        owner: planOwner,
        getIdentity: () => identityRef.current,
        flush: () => flushPendingProjectSaves({ commitActiveField: true }),
        execute: (ownerProjectId, planId, mutates) => api.executePsykeConsoleCommand(
          ownerProjectId,
          { plan_id: planId, confirmed: true },
          mutates,
        ),
      });
      if (!openRef.current
        || !requests.isCurrent(token)
        || !planOwnerMatches(planOwner, identityRef.current.projectId, identityRef.current.sceneId)) return;
      setPlan(null);
      setPlanOwner(null);
      const navigated = result.target_type === "scene"
        ? await onNavigate("manuscript", { sceneId: result.target_id })
        : await onNavigate("psyke", { psykeEntryId: result.target_id });
      if (!openRef.current || !requests.isCurrent(token)) return;
      if (!navigated) {
        setActionError(`${result.message} The resulting target could not be opened.`);
        setMessage("");
        return;
      }
      closeNow();
    } catch (error) {
      if (!openRef.current || !requests.isCurrent(token)) return;
      const keepPlan = error instanceof PendingProjectSaveError;
      if (!keepPlan) {
        setPlan(null);
        setPlanOwner(null);
      }
      const detail = errorMessage(
        error instanceof StaleOmniboxPlanError
          ? "Command not executed."
          : "Command not executed because the workspace could not complete it.",
        error,
      );
      setActionError(detail);
      setMessage("");
      onError?.(error, plan.normalized_command);
      ownerWindow?.requestAnimationFrame(() => (keepPlan ? confirmRef.current : inputRef.current)?.focus());
    } finally {
      executingRef.current = false;
      if (openRef.current && requests.isCurrent(token)) setExecuting(false);
    }
  }, [api, closeNow, onError, onNavigate, ownerWindow, plan, planOwner, requests]);

  const onInputKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((current) => moveOmniboxSelection(flatItems, current, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex((current) => moveOmniboxSelection(flatItems, current, -1));
    } else if (event.key === "Home") {
      event.preventDefault();
      setSelectedIndex(firstEnabledOmniboxIndex(flatItems));
    } else if (event.key === "End") {
      event.preventDefault();
      setSelectedIndex(moveOmniboxSelection(flatItems, 0, -1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const selected = flatItems[selectedIndex];
      if (selected) activateViewItem(selected);
      else if (slashQuery && query.trim().length > 1) planCommand(query);
    } else if (event.key === "Escape" && (planning || plan)) {
      event.preventDefault();
      event.stopPropagation();
      cancelPlan();
    }
  };

  if (!open) return null;

  const liveStatus = actionError
    || suggestionError
    || projectSearchError
    || message
    || (projectSearchLoading ? "Searching current project" : `${flatItems.length} omnibox results`);
  return (
    <ModalPortal>
      <div
        data-lf-modal-layer
        data-screen-label="Studio Omnibox"
        style={backdropStyle}
        onMouseDown={(event) => {
          if (event.target === event.currentTarget && !activating && !executing && !plan) requestClose();
        }}
      >
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-label="Studio omnibox"
          aria-describedby={descriptionId}
          aria-busy={activating || planning || executing}
          tabIndex={-1}
          style={dialogStyle}
        >
          <p id={descriptionId} style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0,0,0,0)" }}>
            Search commands, panels, scenes, notes, PSYKE entries, comments, and recent projects. Type a slash command to preview it before execution.
          </p>
          <input
            ref={inputRef}
            role="combobox"
            aria-label="Search the current project"
            aria-autocomplete="list"
            aria-expanded={plan == null && flatItems.length > 0}
            aria-controls={plan == null ? listId : undefined}
            aria-activedescendant={plan == null ? activeOptionId : undefined}
            value={query}
            maxLength={500}
            disabled={planning || executing || plan != null}
            onChange={(event) => {
              setQuery(event.target.value);
              setSelectedIndex(-1);
              setActionError("");
              setMessage("");
            }}
            onKeyDown={onInputKeyDown}
            placeholder="Search commands, panels, scenes, notes, PSYKE, comments, projects · type / for commands"
            style={inputStyle}
          />

          {plan ? (
            <section
              role="group"
              aria-labelledby={planTitleId}
              aria-describedby={planDescriptionId}
              aria-busy={executing}
              onKeyDown={(event) => {
                if (event.key === "Escape" && !executing) {
                  event.preventDefault();
                  event.stopPropagation();
                  cancelPlan();
                }
              }}
              style={{ padding: "16px 18px", overflowY: "auto" }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 14, alignItems: "baseline" }}>
                <strong id={planTitleId} style={{ color: plan.mutates ? "var(--amber)" : "var(--accent)", fontSize: 9, letterSpacing: ".15em" }}>
                  {plan.mutates ? "PROJECT CHANGE · CONFIRMATION REQUIRED" : "NAVIGATION · REVIEW"}
                </strong>
                <code style={{ color: "var(--txt3)", fontSize: 9 }}>{plan.normalized_command}</code>
              </div>
              <p id={planDescriptionId} style={{ margin: "10px 0 0", color: "var(--strong)", fontSize: 12 }}>{plan.summary}</p>
              <ul style={{ margin: "9px 0 0", paddingLeft: 20, fontSize: 10, lineHeight: 1.6 }}>
                {plan.effects.map((effect) => <li key={effect}>{effect}</li>)}
              </ul>
              {plan.mutates && <p style={{ color: "var(--amber)", fontSize: 9 }}>Nothing changes until you confirm. The core plan is short-lived and single-use.</p>}
              {actionError && <div role="alert" style={{ marginTop: 9, color: "var(--crimson)", fontSize: 10 }}>{actionError}</div>}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
                <button type="button" disabled={executing} onClick={() => cancelPlan()} style={{ ...actionButtonStyle, opacity: executing ? .5 : 1 }}>CANCEL · ESC</button>
                <button
                  ref={confirmRef}
                  type="button"
                  disabled={executing}
                  onClick={() => { void runPlan(); }}
                  style={{ ...actionButtonStyle, borderColor: plan.mutates ? "var(--amber)" : "var(--accent)", color: plan.mutates ? "var(--amber)" : "var(--strong)", opacity: executing ? .6 : 1 }}
                >
                  {executing ? "WORKING…" : plan.requires_confirmation ? "CONFIRM & RUN" : "OPEN TARGET"}
                </button>
              </div>
            </section>
          ) : (
            <div id={listId} role="listbox" aria-label="Omnibox results" style={{ flex: 1, minHeight: 80, maxHeight: "58vh", overflowY: "auto", padding: 7 }}>
              {viewSections.map((section) => {
                const groupId = `${idPrefix}-group-${section.group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
                return (
                  <div key={section.group} role="group" aria-labelledby={groupId} style={{ marginBottom: 7 }}>
                    <div id={groupId} style={{ padding: "6px 11px 4px", color: "var(--txt3)", fontSize: 8, letterSpacing: ".17em" }}>{section.group.toUpperCase()}</div>
                    {section.items.map((item) => {
                      const index = flatItems.findIndex((candidate) => candidate.key === item.key);
                      const selected = index === selectedIndex;
                      return (
                        <button
                          key={item.key}
                          id={omniboxOptionDomId(idPrefix, item.key)}
                          type="button"
                          role="option"
                          aria-selected={selected}
                          aria-disabled={item.disabled}
                          tabIndex={-1}
                          disabled={item.disabled}
                          onMouseEnter={() => { if (!item.disabled) setSelectedIndex(index); }}
                          onClick={() => activateViewItem(item)}
                          style={{ ...optionStyle, cursor: item.disabled ? "default" : "pointer", opacity: item.disabled ? .48 : 1, background: selected ? "var(--tint2)" : "transparent" }}
                        >
                          <span style={{ minWidth: 0 }}>
                            <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--strong)", fontSize: 12 }}>{item.label}</span>
                            <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--txt3)", fontSize: 9, marginTop: 2 }}>{item.detail}</span>
                          </span>
                          {item.shortcut && <kbd style={{ color: "var(--txt3)", fontSize: 8, border: "1px solid var(--line2)", padding: "2px 5px" }}>{item.shortcut}</kbd>}
                        </button>
                      );
                    })}
                  </div>
                );
              })}
              {viewSections.length === 0 && !projectSearchLoading && !suggestionsLoading && (
                <div role="status" style={{ padding: 24, textAlign: "center", color: "var(--txt3)", fontSize: 11 }}>No matches</div>
              )}
            </div>
          )}

          <footer style={{ minHeight: 32, display: "flex", alignItems: "center", gap: 12, padding: "7px 12px", borderTop: "1px solid var(--line2)", color: "var(--txt3)", fontSize: 8 }}>
            <span>{projectSearchLoading ? "SEARCHING PROJECT…" : suggestionsLoading ? "SEARCHING COMMANDS…" : activating ? "SAVING & OPENING…" : planning ? "PLANNING…" : executing ? "EXECUTING…" : "↑↓ NAVIGATE · ENTER OPEN · ESC CLOSE"}</span>
            {(projectSearchError || suggestionError || actionError) && <span role="alert" style={{ marginLeft: "auto", maxWidth: "70%", color: "var(--crimson)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{actionError || suggestionError || projectSearchError}</span>}
          </footer>
          <span role="status" aria-live="polite" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0,0,0,0)" }}>{liveStatus}</span>
        </div>
      </div>
    </ModalPortal>
  );
}
