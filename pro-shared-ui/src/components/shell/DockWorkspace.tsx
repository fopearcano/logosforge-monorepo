import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
  type ReactNode,
} from "react";
import {
  DOCK_SIZE,
  NAVIGATOR_SIZE,
  getWorkspaceVisibility,
  type WorkspaceLayout,
} from "../../workspace/layoutModel";
import {
  focusAfterWorkspaceAction,
  workspacePanelDomToken,
  type WorkspaceActionResult,
} from "./workspaceInteraction";

export const WORKSPACE_DOCK_REGIONS = ["center", "right", "bottom"] as const;
export type WorkspaceDockRegion = (typeof WORKSPACE_DOCK_REGIONS)[number];

export interface WorkspacePanelDefinition {
  /** Durable registry key. Persist this value; never persist the display label. */
  id: string;
  label: string;
  node: ReactNode;
  /** The manuscript is intentionally non-closable; other panels default true. */
  closable?: boolean;
  /** Permanent surfaces can opt out of drag and keyboard movement. */
  movable?: boolean;
  /** Removes the standard content inset for a panel that supplies its own chrome. */
  flush?: boolean;
}

export interface DockWorkspaceProps {
  layout: WorkspaceLayout;
  /** Supply only panels currently opened by the layout. */
  panels: readonly WorkspacePanelDefinition[];
  disabled?: boolean;
  onActivate: (panelId: string, region: WorkspaceDockRegion) => WorkspaceActionResult;
  onMove: (panelId: string, region: WorkspaceDockRegion, index: number) => WorkspaceActionResult;
  onClose: (panelId: string) => WorkspaceActionResult;
  onToggleDock: (region: Exclude<WorkspaceDockRegion, "center">) => WorkspaceActionResult;
  onResizeDock: (region: "right" | "bottom", sizePx: number) => void;
  onReset: () => WorkspaceActionResult;
}

export interface WorkspaceNavigatorProps {
  collapsed: boolean;
  widthPx: number;
  disabled?: boolean;
  children: ReactNode;
  onCollapsedChange: (collapsed: boolean) => WorkspaceActionResult;
  onWidthChange: (widthPx: number) => void;
}

const DRAG_MIME = "application/x-logosforge-workspace-panel";
const DOCK_SEPARATOR_PX = 8;
const DOCK_HEADER_PX = 34;
const MIN_CENTER_WIDTH_PX = 280;
const MIN_CENTER_HEIGHT_PX = 180;

function regionForPanel(layout: WorkspaceLayout, panelId: string): WorkspaceDockRegion | null {
  for (const region of WORKSPACE_DOCK_REGIONS) {
    if (layout.docks[region].panelIds.includes(panelId)) return region;
  }
  return null;
}

function DockHeader({
  region,
  layout,
  workspaceRef,
  panelById,
  disabled,
  onActivate,
  onMove,
  onClose,
  onToggleDock,
  onReset,
}: {
  region: WorkspaceDockRegion;
  layout: WorkspaceLayout;
  workspaceRef: RefObject<HTMLDivElement>;
  panelById: ReadonlyMap<string, WorkspacePanelDefinition>;
  disabled: boolean;
  onActivate: DockWorkspaceProps["onActivate"];
  onMove: DockWorkspaceProps["onMove"];
  onClose: DockWorkspaceProps["onClose"];
  onToggleDock: DockWorkspaceProps["onToggleDock"];
  onReset: DockWorkspaceProps["onReset"];
}) {
  const dock = layout.docks[region];
  const visiblePanelIds = layout.preset === "focus" && region === "center"
    ? dock.panelIds.filter((id) => id === "manuscript")
    : dock.panelIds;
  const activePanelId = layout.preset === "focus" && region === "center"
    ? "manuscript"
    : dock.activePanelId;
  const entries = visiblePanelIds.flatMap((id) => {
    const panel = panelById.get(id);
    return panel ? [panel] : [];
  });

  const activateAt = useCallback((index: number) => {
    const panel = entries[index];
    return panel ? onActivate(panel.id, region) : false;
  }, [entries, onActivate, region]);

  const onTabsKeyDown = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!(event.target instanceof HTMLElement) || event.target.getAttribute("role") !== "tab") return;
    const currentIndex = entries.findIndex((panel) => panel.id === activePanelId);
    if (currentIndex < 0 || entries.length === 0) return;
    let nextIndex: number | null = null;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + entries.length) % entries.length;
    else if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % entries.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = entries.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const nextPanel = entries[nextIndex];
    const previousPanelId = activePanelId;
    focusAfterWorkspaceAction(
      activateAt(nextIndex),
      () => nextPanel
        ? workspaceRef.current?.querySelector<HTMLElement>(
          `#lf-tab-${workspacePanelDomToken(nextPanel.id)}`,
        )
        : undefined,
      () => previousPanelId
        ? workspaceRef.current?.querySelector<HTMLElement>(
          `#lf-tab-${workspacePanelDomToken(previousPanelId)}`,
        )
        : undefined,
    );
  }, [activateAt, activePanelId, entries, workspaceRef]);

  const onDrop = useCallback((event: ReactDragEvent) => {
    event.preventDefault();
    const panelId = event.dataTransfer.getData(DRAG_MIME)
      || event.dataTransfer.getData("text/plain");
    if (panelId && panelById.has(panelId)) onMove(panelId, region, dock.panelIds.length);
  }, [dock.panelIds.length, onMove, panelById, region]);

  return (
    <div
      className={`lf-dock-header lf-dock-header-${region}`}
      data-dock-drop-region={region}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes(DRAG_MIME)) event.preventDefault();
      }}
      onDrop={onDrop}
    >
      <div
        className="lf-dock-tabs"
        role="tablist"
        aria-label={`${region[0]!.toUpperCase()}${region.slice(1)} workspace dock`}
        onKeyDown={onTabsKeyDown}
      >
        {entries.map((panel) => {
          const active = activePanelId === panel.id;
          const nextRegion = WORKSPACE_DOCK_REGIONS[
            (WORKSPACE_DOCK_REGIONS.indexOf(region) + 1) % WORKSPACE_DOCK_REGIONS.length
          ]!;
          return (
            <div className="lf-dock-tab-group" key={panel.id}>
              <button
                type="button"
                id={`lf-tab-${workspacePanelDomToken(panel.id)}`}
                className="lf-dock-tab"
                role="tab"
                aria-selected={active}
                aria-controls={`lf-panel-${workspacePanelDomToken(panel.id)}`}
                tabIndex={active ? 0 : -1}
                draggable={!disabled && panel.movable !== false}
                disabled={disabled}
                onDragStart={(event) => {
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData(DRAG_MIME, panel.id);
                  event.dataTransfer.setData("text/plain", panel.id);
                }}
                onClick={() => {
                  const previousPanelId = activePanelId;
                  focusAfterWorkspaceAction(
                    onActivate(panel.id, region),
                    () => workspaceRef.current?.querySelector<HTMLElement>(
                      `#lf-tab-${workspacePanelDomToken(panel.id)}`,
                    ),
                    () => previousPanelId
                      ? workspaceRef.current?.querySelector<HTMLElement>(
                        `#lf-tab-${workspacePanelDomToken(previousPanelId)}`,
                      )
                      : undefined,
                  );
                }}
              >
                {panel.label}
              </button>
              {panel.movable !== false && (
                <button
                  type="button"
                  className="lf-dock-tab-action"
                  disabled={disabled}
                  aria-label={`Move ${panel.label} to ${nextRegion} dock`}
                  title={`Move to ${nextRegion} dock`}
                  onClick={() => {
                    focusAfterWorkspaceAction(
                      onMove(panel.id, nextRegion, layout.docks[nextRegion].panelIds.length),
                      () => workspaceRef.current?.querySelector<HTMLElement>(
                        `#lf-tab-${workspacePanelDomToken(panel.id)}`,
                      ),
                    );
                  }}
                >
                  ↦
                </button>
              )}
              {panel.closable !== false && (
                <button
                  type="button"
                  className="lf-dock-tab-action"
                  disabled={disabled}
                  aria-label={`Close ${panel.label}`}
                  title={`Close ${panel.label}`}
                  onClick={() => {
                    focusAfterWorkspaceAction(
                      onClose(panel.id),
                      () => workspaceRef.current?.querySelector<HTMLElement>(
                        `[data-dock-drop-region="${region}"] [role="tab"][aria-selected="true"]`,
                      ) ?? workspaceRef.current?.querySelector<HTMLElement>(
                        '[data-dock-drop-region="center"] [role="tab"][aria-selected="true"]',
                      ),
                    );
                  }}
                >
                  ×
                </button>
              )}
            </div>
          );
        })}
      </div>
      <div className="lf-dock-header-actions">
        {region === "center" ? (
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              focusAfterWorkspaceAction(
                onReset(),
                () => workspaceRef.current?.querySelector<HTMLElement>(
                  `#lf-tab-${workspacePanelDomToken("manuscript")}`,
                ),
              );
            }}
            title="Restore the default workspace layout"
          >
            RESET
          </button>
        ) : (
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              focusAfterWorkspaceAction(
                onToggleDock(region),
                () => workspaceRef.current?.querySelector<HTMLElement>(`[aria-label="Expand ${region} dock"]`),
              );
            }}
            aria-label={`Collapse ${region} dock`}
            title={`Collapse ${region} dock`}
          >
            {region === "right" ? "›" : "⌄"}
          </button>
        )}
      </div>
    </div>
  );
}

function DockResizer({
  region,
  value,
  workspaceRef,
  disabled,
  onChange,
}: {
  region: "right" | "bottom";
  value: number;
  workspaceRef: RefObject<HTMLDivElement>;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  const dragging = useRef(false);
  const limits = DOCK_SIZE[region];
  const vertical = region === "right";
  const [metrics, setMetrics] = useState<{ extent: number; maximum: number }>({
    extent: value,
    maximum: limits.max,
  });

  const cleanup = useCallback(() => {
    dragging.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);
  useEffect(() => cleanup, [cleanup]);
  useEffect(() => {
    if (disabled) cleanup();
  }, [cleanup, disabled]);

  const availableMaximum = useCallback(() => {
    const bounds = workspaceRef.current?.getBoundingClientRect();
    if (!bounds) return limits.max;
    const available = vertical
      ? bounds.width - MIN_CENTER_WIDTH_PX - DOCK_SEPARATOR_PX
      : bounds.height - DOCK_HEADER_PX - DOCK_SEPARATOR_PX - DOCK_HEADER_PX - MIN_CENTER_HEIGHT_PX;
    return Math.max(0, Math.min(limits.max, Math.round(available)));
  }, [limits.max, vertical, workspaceRef]);

  const readRenderedExtent = useCallback(() => {
    const panel = workspaceRef.current?.querySelector<HTMLElement>(`.lf-dock-panel-${region}:not([hidden])`);
    if (!panel) return Math.min(value, availableMaximum());
    const bounds = panel.getBoundingClientRect();
    return Math.max(0, Math.round(vertical ? bounds.width : bounds.height));
  }, [availableMaximum, region, value, vertical, workspaceRef]);

  useEffect(() => {
    const root = workspaceRef.current;
    if (!root) return;
    const updateMetrics = () => {
      const next = { extent: readRenderedExtent(), maximum: availableMaximum() };
      setMetrics((current) => current.extent === next.extent && current.maximum === next.maximum
        ? current
        : next);
    };
    updateMetrics();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(updateMetrics);
    observer.observe(root);
    const panel = root.querySelector<HTMLElement>(`.lf-dock-panel-${region}:not([hidden])`);
    if (panel) observer.observe(panel);
    return () => observer.disconnect();
  }, [availableMaximum, readRenderedExtent, region, value, workspaceRef]);

  const clamp = useCallback((next: number) => {
    const maximum = availableMaximum();
    const minimum = Math.min(limits.min, maximum);
    return Math.max(minimum, Math.min(maximum, Math.round(next)));
  }, [availableMaximum, limits.min]);

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (disabled || !dragging.current) return;
    const bounds = workspaceRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const requested = vertical
      ? bounds.right - event.clientX
      : bounds.bottom - event.clientY - DOCK_HEADER_PX;
    onChange(clamp(requested));
  }, [clamp, disabled, onChange, vertical, workspaceRef]);

  const onKeyDown = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const step = event.shiftKey ? 64 : 16;
    let next: number | null = null;
    if (vertical && event.key === "ArrowLeft") next = metrics.extent + step;
    else if (vertical && event.key === "ArrowRight") next = metrics.extent - step;
    else if (!vertical && event.key === "ArrowUp") next = metrics.extent + step;
    else if (!vertical && event.key === "ArrowDown") next = metrics.extent - step;
    else if (event.key === "Home") next = limits.min;
    else if (event.key === "End") next = metrics.maximum;
    if (next === null) return;
    event.preventDefault();
    onChange(clamp(next));
  }, [clamp, disabled, limits.min, metrics.extent, metrics.maximum, onChange, vertical]);

  const ariaMinimum = Math.min(limits.min, metrics.maximum);
  const ariaValue = Math.max(ariaMinimum, Math.min(metrics.maximum, metrics.extent));

  return (
    <div
      className={`lf-dock-resizer lf-dock-resizer-${region}`}
      role="separator"
      aria-label={`Resize ${region} workspace dock`}
      aria-orientation={vertical ? "vertical" : "horizontal"}
      aria-valuemin={ariaMinimum}
      aria-valuemax={metrics.maximum}
      aria-valuenow={ariaValue}
      aria-valuetext={`${ariaValue} pixels${ariaValue !== value ? ` (preferred ${value})` : ""}`}
      tabIndex={disabled ? -1 : 0}
      onKeyDown={onKeyDown}
      onPointerDown={(event) => {
        if (disabled) return;
        dragging.current = true;
        event.currentTarget.setPointerCapture(event.pointerId);
        document.body.style.cursor = vertical ? "col-resize" : "row-resize";
        document.body.style.userSelect = "none";
      }}
      onPointerMove={onPointerMove}
      onPointerUp={cleanup}
      onPointerCancel={cleanup}
      onLostPointerCapture={cleanup}
      title={`Drag to resize the ${region} dock; arrow keys also work`}
    />
  );
}

/** Persistable Navigator frame used in WorkspaceShell.navSlot. */
export function WorkspaceNavigator({
  collapsed,
  widthPx,
  disabled = false,
  children,
  onCollapsedChange,
  onWidthChange,
}: WorkspaceNavigatorProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const clamp = useCallback((value: number) => Math.max(
    NAVIGATOR_SIZE.min,
    Math.min(NAVIGATOR_SIZE.max, Math.round(value)),
  ), []);
  const cleanup = useCallback(() => {
    dragging.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);
  useEffect(() => cleanup, [cleanup]);
  useEffect(() => {
    if (disabled) cleanup();
  }, [cleanup, disabled]);

  if (collapsed) {
    return (
      <aside className="lf-workspace-navigator-collapsed">
        <button
          type="button"
          disabled={disabled}
          onClick={(event) => {
            const shell = event.currentTarget.closest<HTMLElement>(".lf-shell");
            focusAfterWorkspaceAction(
              onCollapsedChange(false),
              () => shell?.querySelector<HTMLElement>(".lf-workspace-navigator-collapse"),
            );
          }}
          aria-label="Expand workspace navigator"
        >
          › NAV
        </button>
      </aside>
    );
  }

  return (
    <div ref={rootRef} className="lf-workspace-navigator" style={{ width: widthPx }}>
      <div className="lf-workspace-navigator-content">{children}</div>
      <button
        type="button"
        className="lf-workspace-navigator-collapse"
        disabled={disabled}
        onClick={(event) => {
          const shell = event.currentTarget.closest<HTMLElement>(".lf-shell");
          focusAfterWorkspaceAction(
            onCollapsedChange(true),
            () => shell?.querySelector<HTMLElement>(".lf-workspace-navigator-collapsed button"),
          );
        }}
        aria-label="Collapse workspace navigator"
        title="Collapse navigator"
      >
        ‹
      </button>
      <div
        className="lf-workspace-navigator-resizer"
        role="separator"
        aria-label="Resize workspace navigator"
        aria-orientation="vertical"
        aria-valuemin={NAVIGATOR_SIZE.min}
        aria-valuemax={NAVIGATOR_SIZE.max}
        aria-valuenow={widthPx}
        tabIndex={disabled ? -1 : 0}
        onKeyDown={(event) => {
          if (disabled) return;
          const step = event.shiftKey ? 64 : 16;
          let next: number | null = null;
          if (event.key === "ArrowLeft") next = widthPx - step;
          else if (event.key === "ArrowRight") next = widthPx + step;
          else if (event.key === "Home") next = NAVIGATOR_SIZE.min;
          else if (event.key === "End") next = NAVIGATOR_SIZE.max;
          if (next === null) return;
          event.preventDefault();
          onWidthChange(clamp(next));
        }}
        onPointerDown={(event) => {
          if (disabled) return;
          dragging.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          document.body.style.cursor = "col-resize";
          document.body.style.userSelect = "none";
        }}
        onPointerMove={(event) => {
          if (disabled || !dragging.current) return;
          const bounds = rootRef.current?.getBoundingClientRect();
          if (bounds) onWidthChange(clamp(event.clientX - bounds.left));
        }}
        onPointerUp={cleanup}
        onPointerCancel={cleanup}
        onLostPointerCapture={cleanup}
        title="Drag to resize the navigator; arrow keys also work"
      />
    </div>
  );
}

/**
 * A three-region work surface whose panel wrappers always remain children of
 * one stable React parent. Moving a tab changes its CSS grid coordinates; it
 * does not reparent/remount editors, chat sessions, or their pending state.
 */
export function DockWorkspace({
  layout,
  panels,
  disabled = false,
  onActivate,
  onMove,
  onClose,
  onToggleDock,
  onResizeDock,
  onReset,
}: DockWorkspaceProps) {
  const workspaceRef = useRef<HTMLDivElement>(null);
  const panelById = useMemo(() => new Map(panels.map((panel) => [panel.id, panel])), [panels]);
  const visibility = getWorkspaceVisibility(layout);
  const focus = layout.preset === "focus";
  const rightHasPanels = layout.docks.right.panelIds.length > 0;
  const bottomHasPanels = layout.docks.bottom.panelIds.length > 0;
  const rightVisible = visibility.docks.right;
  const bottomVisible = visibility.docks.bottom;
  const rightExtent = focus || !rightHasPanels ? 0 : rightVisible ? layout.docks.right.sizePx : 34;
  const bottomHeaderExtent = focus || !bottomHasPanels ? 0 : bottomVisible ? 34 : 28;
  const bottomBodyExtent = bottomVisible ? layout.docks.bottom.sizePx : 0;
  // Persist the writer's preferred sizes, but project them through soft center
  // minimums at render time. A maximized navigator plus a maximized right or
  // bottom dock must never squeeze the manuscript track to zero.
  const rightTrack = rightVisible
    ? `min(${rightExtent}px, max(0px, calc(100% - ${MIN_CENTER_WIDTH_PX + DOCK_SEPARATOR_PX}px)))`
    : `${rightExtent}px`;
  const bottomTrack = bottomVisible
    ? `min(${bottomBodyExtent}px, max(0px, calc(100% - ${
      DOCK_HEADER_PX + DOCK_SEPARATOR_PX + DOCK_HEADER_PX + MIN_CENTER_HEIGHT_PX
    }px)))`
    : "0px";

  const rootStyle = {
    gridTemplateColumns: `minmax(0, 1fr) ${rightVisible ? DOCK_SEPARATOR_PX : 0}px ${rightTrack}`,
    gridTemplateRows: `${DOCK_HEADER_PX}px minmax(0, 1fr) ${
      bottomVisible ? DOCK_SEPARATOR_PX : 0
    }px ${bottomHeaderExtent}px ${bottomTrack}`,
  };

  return (
    <div
      ref={workspaceRef}
      className="lf-dock-workspace"
      data-screen-label="Studio Dock Workspace"
      data-workspace-preset={layout.preset}
      aria-busy={disabled || undefined}
      style={rootStyle}
    >
      <DockHeader
        region="center"
        layout={layout}
        workspaceRef={workspaceRef}
        panelById={panelById}
        disabled={disabled}
        onActivate={onActivate}
        onMove={onMove}
        onClose={onClose}
        onToggleDock={onToggleDock}
        onReset={onReset}
      />
      {rightVisible && (
        <DockHeader
          region="right"
          layout={layout}
          workspaceRef={workspaceRef}
          panelById={panelById}
          disabled={disabled}
          onActivate={onActivate}
          onMove={onMove}
          onClose={onClose}
          onToggleDock={onToggleDock}
          onReset={onReset}
        />
      )}
      {bottomVisible && (
        <DockHeader
          region="bottom"
          layout={layout}
          workspaceRef={workspaceRef}
          panelById={panelById}
          disabled={disabled}
          onActivate={onActivate}
          onMove={onMove}
          onClose={onClose}
          onToggleDock={onToggleDock}
          onReset={onReset}
        />
      )}

      {rightVisible && (
        <DockResizer
          region="right"
          value={layout.docks.right.sizePx}
          workspaceRef={workspaceRef}
          disabled={disabled}
          onChange={(value) => onResizeDock("right", value)}
        />
      )}
      {bottomVisible && (
        <DockResizer
          region="bottom"
          value={layout.docks.bottom.sizePx}
          workspaceRef={workspaceRef}
          disabled={disabled}
          onChange={(value) => onResizeDock("bottom", value)}
        />
      )}

      {!focus && rightHasPanels && !rightVisible && (
        <button
          type="button"
          className="lf-dock-collapsed lf-dock-collapsed-right"
          disabled={disabled}
          onClick={() => {
            focusAfterWorkspaceAction(
              onToggleDock("right"),
              () => workspaceRef.current?.querySelector<HTMLElement>(
                '[data-dock-drop-region="right"] [role="tab"][aria-selected="true"]',
              ),
            );
          }}
          aria-label="Expand right dock"
        >
          ‹ RIGHT
        </button>
      )}
      {!focus && bottomHasPanels && !bottomVisible && (
        <button
          type="button"
          className="lf-dock-collapsed lf-dock-collapsed-bottom"
          disabled={disabled}
          onClick={() => {
            focusAfterWorkspaceAction(
              onToggleDock("bottom"),
              () => workspaceRef.current?.querySelector<HTMLElement>(
                '[data-dock-drop-region="bottom"] [role="tab"][aria-selected="true"]',
              ),
            );
          }}
          aria-label="Expand bottom dock"
        >
          ↑ BOTTOM
        </button>
      )}

      <div className="lf-dock-panel-layer">
        {panels.map((panel) => {
          const region = regionForPanel(layout, panel.id);
          if (region === null) return null;
          const dock = layout.docks[region];
          const active = focus && region === "center"
            ? panel.id === "manuscript"
            : dock.activePanelId === panel.id;
          const visible = active && visibility.docks[region];
          const grid = region === "center"
            ? { gridColumn: "1", gridRow: "2" }
            : region === "right"
              ? { gridColumn: "3", gridRow: "2" }
              : { gridColumn: "1 / 4", gridRow: "5" };
          return (
            <section
              key={panel.id}
              id={`lf-panel-${workspacePanelDomToken(panel.id)}`}
              className={`lf-dock-panel lf-dock-panel-${region}${panel.flush ? " lf-dock-panel-flush" : ""}`}
              role="tabpanel"
              aria-labelledby={`lf-tab-${workspacePanelDomToken(panel.id)}`}
              aria-hidden={!visible}
              hidden={!visible}
              data-panel-id={panel.id}
              data-dock-region={region}
              style={grid}
            >
              {panel.node}
            </section>
          );
        })}
      </div>
    </div>
  );
}
