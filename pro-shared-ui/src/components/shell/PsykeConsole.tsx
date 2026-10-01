import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import type {
  PsykeConsoleCommandPlanDTO,
  PsykeConsoleSuggestionDTO,
} from "@logosforge/ui-contracts";
import { flushPendingProjectSaves } from "../../adapters/projectSaveCoordinator";
import { useSelection } from "../../adapters/selection";
import { useNavigate, useStudio } from "../../adapters/StudioProvider";
import { createLatestRequestGate } from "../../hooks/latestRequest";

const resultButton: CSSProperties = {
  width: "100%",
  minHeight: 36,
  display: "grid",
  gridTemplateColumns: "28px minmax(0,1fr) auto",
  alignItems: "center",
  gap: 9,
  padding: "6px 10px",
  border: "none",
  borderBottom: "1px solid var(--line2)",
  color: "var(--txt)",
  font: "inherit",
  textAlign: "left",
  cursor: "pointer",
};

const planButton: CSSProperties = {
  minHeight: 28,
  padding: "4px 12px",
  border: "1px solid var(--line2)",
  background: "var(--panel2)",
  color: "var(--txt)",
  font: "inherit",
  fontSize: 9,
  letterSpacing: ".1em",
  cursor: "pointer",
};

const visuallyHidden: CSSProperties = {
  position: "absolute",
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: "hidden",
  clip: "rect(0,0,0,0)",
  whiteSpace: "nowrap",
  border: 0,
};

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.matches("input, textarea, select, [contenteditable='true'], [contenteditable='plaintext-only']")
    || target.closest("[contenteditable='true'], [contenteditable='plaintext-only']") != null;
}

function errorText(prefix: string, error: unknown): string {
  return `${prefix} ${error instanceof Error ? error.message : String(error)}`;
}

/**
 * The live PSYKE omnibox. Ranking, parsing, target resolution, and execution
 * authority remain in the Python core. React only manages request lifetime,
 * an explicit inline review step, the save barrier, and returned navigation.
 */
export function PsykeConsole() {
  const { api, projectId } = useStudio();
  const navigate = useNavigate();
  const { selection } = useSelection();
  const inputRef = useRef<HTMLInputElement>(null);
  const runButtonRef = useRef<HTMLButtonElement>(null);
  const skipNextQuerySearch = useRef(false);
  const searchTimerRef = useRef<number | null>(null);
  const searchAbortRef = useRef<AbortController | null>(null);
  const planAbortRef = useRef<AbortController | null>(null);
  const executingRef = useRef(false);
  const planOwnerRef = useRef<{ projectId: number; planId: string } | null>(null);
  const requests = useRef(createLatestRequestGate()).current;
  const idPrefix = `lf-psyke-console-${useId().replace(/:/g, "")}`;
  const listId = `${idPrefix}-results`;
  const planTitleId = `${idPrefix}-plan-title`;
  const planDescriptionId = `${idPrefix}-plan-description`;
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PsykeConsoleSuggestionDTO[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [plan, setPlan] = useState<PsykeConsoleCommandPlanDTO | null>(null);
  const [planError, setPlanError] = useState("");
  const [message, setMessage] = useState("");

  const cancelPlan = useCallback((nextMessage = "Command plan cancelled.") => {
    planAbortRef.current?.abort();
    planAbortRef.current = null;
    requests.invalidate("plan");
    planOwnerRef.current = null;
    setPlanning(false);
    setPlan(null);
    setPlanError("");
    setMessage(nextMessage);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [requests]);

  useEffect(() => {
    requests.open();
    return () => {
      searchAbortRef.current?.abort();
      searchAbortRef.current = null;
      planAbortRef.current?.abort();
      planAbortRef.current = null;
      planOwnerRef.current = null;
      requests.close();
    };
  }, [requests]);

  useEffect(() => {
    searchAbortRef.current?.abort();
    searchAbortRef.current = null;
    planAbortRef.current?.abort();
    planAbortRef.current = null;
    requests.invalidate("suggestions");
    requests.invalidate("plan");
    planOwnerRef.current = null;
    setQuery("");
    setResults([]);
    setSelectedIndex(0);
    setExpanded(false);
    setLoading(false);
    setPlanning(false);
    setPlan(null);
    setPlanError("");
    setMessage("");
  }, [projectId, requests]);

  useEffect(() => {
    // Relative scene commands are planned against this exact selection. A
    // context change invalidates the capability before it can be executed.
    const hadPlanOwner = planOwnerRef.current != null;
    planAbortRef.current?.abort();
    planAbortRef.current = null;
    requests.invalidate("plan");
    planOwnerRef.current = null;
    setPlanning(false);
    setPlan(null);
    setPlanError("");
    if (hadPlanOwner) setMessage("");
  }, [requests, selection.sceneId]);

  useEffect(() => {
    const onGlobalKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key !== "/" || isEditableTarget(event.target)) return;
      event.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener("keydown", onGlobalKey);
    return () => window.removeEventListener("keydown", onGlobalKey);
  }, []);

  useEffect(() => {
    if (skipNextQuerySearch.current) {
      skipNextQuerySearch.current = false;
      requests.invalidate("suggestions");
      setResults([]);
      setSelectedIndex(0);
      setExpanded(false);
      setLoading(false);
      return;
    }

    const trimmed = query.trim();
    if (!trimmed || projectId == null) {
      requests.invalidate("suggestions");
      setResults([]);
      setSelectedIndex(0);
      setExpanded(false);
      setLoading(false);
      if (projectId == null && trimmed) setMessage("Open a project to search PSYKE.");
      else setMessage("");
      return;
    }

    requests.invalidate("suggestions");
    setResults([]);
    setSelectedIndex(0);
    setExpanded(false);
    setLoading(true);
    setMessage("");
    const timer = window.setTimeout(() => {
      searchTimerRef.current = null;
      const token = requests.begin("suggestions");
      const controller = new AbortController();
      searchAbortRef.current = controller;
      void api.getPsykeConsoleSuggestions(projectId, trimmed, selection.sceneId, controller.signal).then(
        (next) => {
          if (!requests.isCurrent(token)) return;
          if (searchAbortRef.current === controller) searchAbortRef.current = null;
          setResults(next);
          setSelectedIndex(0);
          setExpanded(true);
          setLoading(false);
          setMessage(next.length === 0 ? "No PSYKE matches. Press Enter to preview a complete slash command." : "");
        },
        (error) => {
          if (!requests.isCurrent(token)) return;
          if (searchAbortRef.current === controller) searchAbortRef.current = null;
          if (error instanceof Error && error.name === "AbortError") return;
          setResults([]);
          setSelectedIndex(0);
          setExpanded(true);
          setLoading(false);
          setMessage(errorText("PSYKE search failed.", error));
        },
      );
    }, 100);
    searchTimerRef.current = timer;
    return () => {
      window.clearTimeout(timer);
      if (searchTimerRef.current === timer) searchTimerRef.current = null;
      searchAbortRef.current?.abort();
      searchAbortRef.current = null;
    };
  }, [api, projectId, query, requests, selection.sceneId]);

  const planCommand = useCallback((rawCommand: string) => {
    const command = rawCommand.trim();
    if (projectId == null) {
      setMessage("Open a project before planning a command.");
      return;
    }
    if (!command.startsWith("/")) {
      setMessage("Only slash commands can be previewed.");
      return;
    }
    if (searchTimerRef.current != null) {
      window.clearTimeout(searchTimerRef.current);
      searchTimerRef.current = null;
    }
    searchAbortRef.current?.abort();
    searchAbortRef.current = null;
    requests.invalidate("suggestions");
    setResults([]);
    setExpanded(false);
    planAbortRef.current?.abort();
    const controller = new AbortController();
    planAbortRef.current = controller;
    const token = requests.begin("plan");
    setPlan(null);
    setPlanError("");
    setPlanning(true);
    setMessage("Planning command…");
    void api.planPsykeConsoleCommand(
      projectId,
      { command, active_scene_id: selection.sceneId },
      controller.signal,
    ).then(
      (nextPlan) => {
        if (!requests.isCurrent(token)) return;
        if (planAbortRef.current === controller) planAbortRef.current = null;
        planOwnerRef.current = { projectId, planId: nextPlan.plan_id };
        setPlanning(false);
        setPlan(nextPlan);
        setPlanError("");
        setMessage(nextPlan.requires_confirmation ? "Review the project change before confirming." : "Review the resolved target before opening it.");
        if (query !== nextPlan.normalized_command) skipNextQuerySearch.current = true;
        setQuery(nextPlan.normalized_command);
        window.requestAnimationFrame(() => runButtonRef.current?.focus());
      },
      (error) => {
        if (!requests.isCurrent(token)) return;
        if (planAbortRef.current === controller) planAbortRef.current = null;
        if (error instanceof Error && error.name === "AbortError") return;
        planOwnerRef.current = null;
        setPlanning(false);
        setPlan(null);
        const detail = errorText("Command preview failed.", error);
        setPlanError(detail);
        setMessage(detail);
        window.requestAnimationFrame(() => inputRef.current?.focus());
      },
    );
  }, [api, projectId, query, requests, selection.sceneId]);

  const activate = useCallback((suggestion: PsykeConsoleSuggestionDTO) => {
    const opensEntry = suggestion.entry_id > 0
      && suggestion.category === "entity"
      && !suggestion.text.startsWith("/");
    if (opensEntry) {
      navigate("PSYKE", { psykeEntryId: suggestion.entry_id });
      if (query !== "") skipNextQuerySearch.current = true;
      setQuery("");
      setResults([]);
      setExpanded(false);
      setMessage(`Requested ${suggestion.text} in the PSYKE Bible.`);
      inputRef.current?.focus();
      return;
    }
    planAbortRef.current?.abort();
    planAbortRef.current = null;
    requests.invalidate("plan");
    planOwnerRef.current = null;
    setPlan(null);
    setPlanError("");
    const nextQuery = suggestion.text.endsWith(" ") ? suggestion.text : `${suggestion.text} `;
    if (nextQuery !== query) skipNextQuerySearch.current = true;
    setQuery(nextQuery);
    setExpanded(false);
    setMessage("Complete the command, then press Enter to preview its exact effect.");
    inputRef.current?.focus();
  }, [navigate, query, requests]);

  const executePlan = useCallback(async () => {
    if (!plan || projectId == null || executingRef.current) return;
    const owner = { projectId, planId: plan.plan_id };
    executingRef.current = true;
    setExecuting(true);
    setPlanError("");
    setMessage("Saving pending edits before command execution…");
    try {
      try {
        await flushPendingProjectSaves({ commitActiveField: true });
      } catch (error) {
        if (planOwnerRef.current?.planId === owner.planId) {
          const detail = errorText("Command not executed because pending edits could not be saved.", error);
          setPlanError(detail);
          setMessage(detail);
          window.requestAnimationFrame(() => runButtonRef.current?.focus());
        }
        return;
      }
      const currentOwner = planOwnerRef.current;
      if (currentOwner?.projectId !== owner.projectId || currentOwner.planId !== owner.planId) return;
      setMessage(plan.mutates ? "Executing confirmed project change…" : "Opening the reviewed target…");
      const result = await api.executePsykeConsoleCommand(
        owner.projectId,
        { plan_id: owner.planId, confirmed: true },
        plan.mutates,
      );
      const resultOwner = planOwnerRef.current;
      if (resultOwner?.projectId !== owner.projectId || resultOwner.planId !== owner.planId) return;
      planOwnerRef.current = null;
      setPlan(null);
      setQuery("");
      setResults([]);
      setExpanded(false);
      setPlanError("");
      setMessage(result.message);
      if (result.target_type === "scene") {
        navigate("Manuscript", { sceneId: result.target_id });
      } else {
        navigate("PSYKE", { psykeEntryId: result.target_id });
      }
    } catch (error) {
      if (planOwnerRef.current?.planId === owner.planId) {
        planOwnerRef.current = null;
        setPlan(null);
        const detail = errorText("Command execution failed; preview it again before retrying.", error);
        setPlanError(detail);
        setMessage(detail);
        window.requestAnimationFrame(() => inputRef.current?.focus());
      }
    } finally {
      executingRef.current = false;
      setExecuting(false);
    }
  }, [api, navigate, plan, projectId]);

  const onKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && results.length) {
      event.preventDefault();
      setExpanded(true);
      setSelectedIndex((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp" && results.length) {
      event.preventDefault();
      setExpanded(true);
      setSelectedIndex((index) => (index - 1 + results.length) % results.length);
    } else if (event.key === "Enter" && expanded && results[selectedIndex]) {
      event.preventDefault();
      activate(results[selectedIndex]);
    } else if (event.key === "Enter" && query.trim().startsWith("/") && !planning) {
      event.preventDefault();
      planCommand(query);
    } else if (event.key === "Escape") {
      event.preventDefault();
      if (executing) return;
      if (plan || planning) {
        cancelPlan();
        return;
      }
      if (searchTimerRef.current != null) {
        window.clearTimeout(searchTimerRef.current);
        searchTimerRef.current = null;
      }
      requests.invalidate("suggestions");
      searchAbortRef.current?.abort();
      searchAbortRef.current = null;
      setLoading(false);
      setExpanded(false);
      setResults([]);
      setMessage("");
      inputRef.current?.blur();
    }
  };

  const activeId = expanded && results[selectedIndex] ? `${listId}-option-${selectedIndex}` : undefined;
  const busy = planning || executing;
  return (
    <div data-screen-label="PSYKE Console" style={{ height: 32, flex: "none", display: "flex", alignItems: "center", gap: 9, padding: "0 14px", background: "var(--panel2)", borderTop: "1px solid var(--line)", position: "relative", zIndex: 28 }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: "var(--accent)", boxShadow: "0 0 10px var(--accent)" }} />
      <span aria-hidden="true" style={{ fontFamily: "'Chakra Petch'", fontWeight: 700, color: "var(--accent)", fontSize: 12 }}>ψ</span>
      <span aria-hidden="true" style={{ color: "var(--accent)" }}>❯</span>
      <input
        ref={inputRef}
        role="combobox"
        aria-label="PSYKE Console"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-activedescendant={activeId}
        value={query}
        disabled={projectId == null || executing}
        onChange={(event) => {
          if (plan || planning) cancelPlan("");
          setQuery(event.target.value);
          setSelectedIndex(0);
        }}
        onFocus={() => { if (results.length || (message && !plan)) setExpanded(true); }}
        onBlur={() => setExpanded(false)}
        onKeyDown={onKeyDown}
        placeholder={projectId == null ? "Open a project to search PSYKE" : "Search the bible · type / for core commands"}
        style={{ flex: 1, minWidth: 0, height: 28, padding: 0, background: "transparent", border: "none", outline: "none", color: "var(--strong)", font: "inherit", fontSize: 11, letterSpacing: ".03em" }}
      />
      {loading && <span aria-hidden="true" style={{ color: "var(--accent)", fontSize: 9 }}>SEARCHING…</span>}
      {planning && <span aria-hidden="true" style={{ color: "var(--amber)", fontSize: 9 }}>PLANNING…</span>}
      {executing && <span aria-hidden="true" style={{ color: "var(--accent)", fontSize: 9 }}>EXECUTING…</span>}
      {!busy && !loading && !expanded && message && <span title={message} style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: message.includes("failed") || message.includes("not executed") ? "var(--crimson)" : "var(--txt3)", fontSize: 8 }}>{message}</span>}
      <span style={{ fontSize: 8, letterSpacing: ".18em", color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 6px" }}>PSYKE · /</span>

      {expanded && (
        <div id={listId} role="listbox" aria-label="PSYKE Console suggestions" style={{ position: "absolute", left: 34, right: 14, bottom: "calc(100% + 1px)", maxHeight: 300, overflowY: "auto", border: "1px solid var(--line)", background: "var(--raised)", boxShadow: "0 -16px 40px rgba(0,0,0,.45)" }}>
          {results.map((suggestion, index) => (
            <button
              key={`${suggestion.category}:${suggestion.text}:${suggestion.entry_id}:${index}`}
              id={`${listId}-option-${index}`}
              role="option"
              aria-selected={index === selectedIndex}
              tabIndex={-1}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setSelectedIndex(index)}
              onClick={() => activate(suggestion)}
              style={{ ...resultButton, background: index === selectedIndex ? "var(--tint2)" : "var(--raised)" }}
            >
              <span aria-hidden="true" style={{ color: suggestion.entry_id > 0 ? "var(--accent)" : "var(--amber)" }}>{suggestion.icon || "ψ"}</span>
              <span style={{ minWidth: 0 }}>
                <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--strong)", fontSize: 11 }}>{suggestion.text}</span>
                <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--txt3)", fontSize: 8 }}>{suggestion.description}</span>
              </span>
              <span style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".12em" }}>{suggestion.category.replaceAll("_", " ").toUpperCase()}</span>
            </button>
          ))}
          {message && results.length === 0 && <div role="status" style={{ minHeight: 42, display: "grid", placeItems: "center", padding: "8px 12px", color: message.includes("failed") ? "var(--crimson)" : "var(--txt3)", fontSize: 9 }}>{message}</div>}
        </div>
      )}

      {plan && (
        <section
          role="group"
          aria-labelledby={planTitleId}
          aria-describedby={planDescriptionId}
          aria-busy={executing}
          onKeyDown={(event) => {
            if (event.key === "Escape" && !executing) {
              event.preventDefault();
              cancelPlan();
            }
          }}
          style={{ position: "absolute", left: 34, right: 14, bottom: "calc(100% + 1px)", padding: "12px 14px", border: `1px solid ${plan.mutates ? "var(--amber)" : "var(--accent)"}`, background: "var(--raised)", boxShadow: "0 -16px 40px rgba(0,0,0,.5)" }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <strong id={planTitleId} style={{ color: plan.mutates ? "var(--amber)" : "var(--accent)", fontSize: 9, letterSpacing: ".16em" }}>
              {plan.mutates ? "PROJECT CHANGE · REVIEW REQUIRED" : "NAVIGATION PLAN · REVIEW"}
            </strong>
            <code style={{ color: "var(--txt3)", fontSize: 9 }}>{plan.normalized_command}</code>
          </div>
          <div id={planDescriptionId} style={{ marginTop: 7, color: "var(--strong)", fontSize: 11 }}>{plan.summary}</div>
          <ul style={{ margin: "7px 0 0", paddingLeft: 18, color: "var(--txt)", fontSize: 9, lineHeight: 1.6 }}>
            {plan.effects.map((effect) => <li key={effect}>{effect}</li>)}
          </ul>
          {plan.mutates && <div style={{ marginTop: 7, color: "var(--amber)", fontSize: 8 }}>Nothing changes until you explicitly confirm. This plan expires shortly and can run only once.</div>}
          {planError && <div role="alert" style={{ marginTop: 7, color: "var(--crimson)", fontSize: 9 }}>{planError}</div>}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 10 }}>
            <button type="button" disabled={executing} onClick={() => cancelPlan()} style={{ ...planButton, opacity: executing ? .5 : 1 }}>CANCEL · ESC</button>
            <button
              ref={runButtonRef}
              type="button"
              disabled={executing}
              onClick={() => { void executePlan(); }}
              style={{ ...planButton, borderColor: plan.mutates ? "var(--amber)" : "var(--accent)", background: plan.mutates ? "color-mix(in srgb, var(--amber) 12%, var(--panel2))" : "var(--tint2)", color: plan.mutates ? "var(--amber)" : "var(--strong)", opacity: executing ? .6 : 1 }}
            >
              {executing ? "WORKING…" : plan.requires_confirmation ? "CONFIRM & RUN" : "OPEN TARGET"}
            </button>
          </div>
        </section>
      )}
      <span style={visuallyHidden} role="status" aria-live="polite">{loading ? "Searching PSYKE" : planning ? "Planning command" : executing ? "Executing command" : message}</span>
    </div>
  );
}
