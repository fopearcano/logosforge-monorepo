import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import {
  DOCK_SIZE,
  FLOATING_PANEL_SIZE,
  NAVIGATOR_SIZE,
  getPanelPlacement,
  getWorkspaceVisibility,
  type FloatingPanelBounds,
  type FloatingPanelLayout,
  type WorkspaceLayout,
} from "../../workspace/layoutModel";
import {
  focusAfterWorkspaceAction,
  workspacePanelDomToken,
  type WorkspaceActionResult,
} from "./workspaceInteraction";
import { PanelHostProvider } from "../common/PanelHost";

export const WORKSPACE_DOCK_REGIONS = ["left", "center", "right", "bottom"] as const;
export type WorkspaceDockRegion = (typeof WORKSPACE_DOCK_REGIONS)[number];

export interface WorkspacePanelDefinition {
  /** Durable registry key. Persist this value; never persist the display label. */
  id: string;
  label: string;
  node: ReactNode;
  /** Permanent surfaces such as Manuscript can opt out of close; others default true. */
  closable?: boolean;
  /** Specialized hosts may opt out; standard Pro panels are all movable. */
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
  onFloat: (panelId: string, bounds?: Partial<FloatingPanelBounds>) => WorkspaceActionResult;
  onClose: (panelId: string) => WorkspaceActionResult;
  onToggleDock: (region: Exclude<WorkspaceDockRegion, "center">) => WorkspaceActionResult;
  onResizeDock: (region: "left" | "right" | "bottom", sizePx: number) => void;
  onMoveFloating: (panelId: string, x: number, y: number) => void;
  onResizeFloating: (panelId: string, width: number, height: number) => void;
  onMinimizeFloating: (panelId: string, minimized: boolean) => WorkspaceActionResult;
  onFocusFloating: (panelId: string) => void;
  onReset: () => WorkspaceActionResult;
  /**
   * Desktop-only host for true operating-system windows. Browser and preview
   * consumers omit this and retain the bounded in-workspace floating fallback.
   */
  externalFloatingWindows?: ExternalFloatingWindowHost;
  /** Native child windows do not bubble keyboard events to their opener. */
  onExternalWindowKeyDown?: (event: KeyboardEvent) => void;
}

export interface ExternalFloatingWindowHost {
  open(
    panelId: string,
    label: string,
    bounds: FloatingPanelBounds,
  ): Window | null;
  /** Authorize and finish closing a host-owned panel window. */
  release(panelId: string): void;
  /** Reveal only after styles and the stable portal host have been adopted. */
  show(panelId: string, activate: boolean): void;
  focus(panelId: string): void;
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
const COLLAPSED_DOCK_PX = 34;
const FLOATING_TITLEBAR_PX = 34;
const FLOATING_VISIBLE_EDGE_PX = 96;

interface WorkspaceViewport {
  width: number;
  height: number;
}

export function projectFloatingBounds(
  bounds: FloatingPanelBounds,
  viewport: WorkspaceViewport,
): FloatingPanelBounds {
  if (viewport.width <= 0 || viewport.height <= 0) return { ...bounds };
  const width = Math.max(1, Math.min(Math.round(bounds.width), Math.round(viewport.width)));
  const height = Math.max(
    FLOATING_TITLEBAR_PX,
    Math.min(Math.round(bounds.height), Math.round(viewport.height)),
  );
  const minX = Math.min(0, viewport.width - FLOATING_VISIBLE_EDGE_PX);
  const maxX = Math.max(minX, viewport.width - Math.min(width, FLOATING_VISIBLE_EDGE_PX));
  const minY = 0;
  const maxY = Math.max(0, viewport.height - FLOATING_TITLEBAR_PX);
  return {
    x: Math.max(minX, Math.min(maxX, Math.round(bounds.x))),
    y: Math.max(minY, Math.min(maxY, Math.round(bounds.y))),
    width,
    height,
  };
}

function findWorkspaceFocusControl(root: HTMLDivElement | null): HTMLElement | undefined {
  if (!root) return undefined;
  const focusedSurface = root.querySelector<HTMLElement>(
    '[data-panel-focused="true"]:not([hidden])',
  );
  const labelledBy = focusedSurface?.getAttribute("aria-labelledby");
  if (labelledBy) {
    const labelledControl = root.querySelector<HTMLElement>(`#${labelledBy}`);
    if (labelledControl) return labelledControl;
  }
  return root.querySelector<HTMLElement>(
    '.lf-floating-panel-active:not([hidden]) .lf-floating-panel-titlebar',
  ) ?? root.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]') ?? undefined;
}

function DockHeader({
  region,
  layout,
  workspaceRef,
  panelById,
  disabled,
  onActivate,
  onMove,
  onFloat,
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
  onFloat: DockWorkspaceProps["onFloat"];
  onClose: DockWorkspaceProps["onClose"];
  onToggleDock: DockWorkspaceProps["onToggleDock"];
  onReset: DockWorkspaceProps["onReset"];
}) {
  const dock = layout.docks[region];
  const visiblePanelIds = layout.preset === "focus" && region === "center"
    ? panelById.has("manuscript") ? ["manuscript"] : []
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
    event.stopPropagation();
    const panelId = event.dataTransfer.getData(DRAG_MIME)
      || event.dataTransfer.getData("text/plain");
    if (panelId && panelById.has(panelId)) {
      const previousPanelId = dock.activePanelId;
      focusAfterWorkspaceAction(
        onMove(panelId, region, dock.panelIds.length),
        () => workspaceRef.current?.querySelector<HTMLElement>(
          `#lf-tab-${workspacePanelDomToken(panelId)}`,
        ),
        () => previousPanelId
          ? workspaceRef.current?.querySelector<HTMLElement>(
            `#lf-tab-${workspacePanelDomToken(previousPanelId)}`,
          )
          : undefined,
      );
    }
  }, [dock.activePanelId, dock.panelIds.length, onMove, panelById, region, workspaceRef]);

  return (
    <div
      className={`lf-dock-header lf-dock-header-${region}`}
      data-dock-drop-region={region}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes(DRAG_MIME)) {
          event.preventDefault();
          event.stopPropagation();
        }
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
          const focusProjection = layout.preset === "focus"
            && region === "center"
            && panel.id === "manuscript";
          const movable = panel.movable !== false && !focusProjection;
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
                draggable={!disabled && movable}
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
              {movable && (
                <>
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
                  <button
                    type="button"
                    className="lf-dock-tab-action"
                    disabled={disabled}
                    aria-label={`Float ${panel.label}`}
                    title={`Float ${panel.label}`}
                    onClick={() => {
                      const bounds = workspaceRef.current?.getBoundingClientRect();
                      const offset = layout.floatingPanels.length * 24;
                      const width = Math.min(
                        FLOATING_PANEL_SIZE.defaultWidth,
                        Math.max(FLOATING_PANEL_SIZE.minWidth, (bounds?.width ?? 760) - 48),
                      );
                      const height = Math.min(
                        FLOATING_PANEL_SIZE.defaultHeight,
                        Math.max(FLOATING_PANEL_SIZE.minHeight, (bounds?.height ?? 560) - 72),
                      );
                      focusAfterWorkspaceAction(
                        onFloat(panel.id, {
                          x: Math.max(16, Math.round(((bounds?.width ?? width) - width) / 2) + offset),
                          y: 48 + offset,
                          width,
                          height,
                        }),
                        () => workspaceRef.current?.querySelector<HTMLElement>(
                          `#lf-floating-title-${workspacePanelDomToken(panel.id)}`,
                        ),
                      );
                    }}
                  >
                    ◇
                  </button>
                </>
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
                      () => findWorkspaceFocusControl(workspaceRef.current),
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
            {region === "left" ? "‹" : region === "right" ? "›" : "⌄"}
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
  oppositeExtent = 0,
  disabled,
  onChange,
}: {
  region: "left" | "right" | "bottom";
  value: number;
  workspaceRef: RefObject<HTMLDivElement>;
  oppositeExtent?: number;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  const dragging = useRef(false);
  const limits = DOCK_SIZE[region];
  const vertical = region !== "bottom";
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
      ? bounds.width - MIN_CENTER_WIDTH_PX - oppositeExtent - (DOCK_SEPARATOR_PX * 2)
      : bounds.height - DOCK_HEADER_PX - DOCK_SEPARATOR_PX - DOCK_HEADER_PX - MIN_CENTER_HEIGHT_PX;
    return Math.max(0, Math.min(limits.max, Math.round(available)));
  }, [limits.max, oppositeExtent, vertical, workspaceRef]);

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
    const requested = region === "left"
      ? event.clientX - bounds.left
      : region === "right"
        ? bounds.right - event.clientX
        : bounds.bottom - event.clientY - DOCK_HEADER_PX;
    onChange(clamp(requested));
  }, [clamp, disabled, onChange, region, workspaceRef]);

  const onKeyDown = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const step = event.shiftKey ? 64 : 16;
    let next: number | null = null;
    if (region === "left" && event.key === "ArrowLeft") next = metrics.extent - step;
    else if (region === "left" && event.key === "ArrowRight") next = metrics.extent + step;
    else if (region === "right" && event.key === "ArrowLeft") next = metrics.extent + step;
    else if (region === "right" && event.key === "ArrowRight") next = metrics.extent - step;
    else if (!vertical && event.key === "ArrowUp") next = metrics.extent + step;
    else if (!vertical && event.key === "ArrowDown") next = metrics.extent - step;
    else if (event.key === "Home") next = limits.min;
    else if (event.key === "End") next = metrics.maximum;
    if (next === null) return;
    event.preventDefault();
    onChange(clamp(next));
  }, [clamp, disabled, limits.min, metrics.extent, metrics.maximum, onChange, region, vertical]);

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

type FloatingInteraction =
  | {
    kind: "move";
    startClientX: number;
    startClientY: number;
    originX: number;
    originY: number;
    restoreX: number;
    restoreY: number;
  }
  | {
    kind: "resize";
    startClientX: number;
    startClientY: number;
    originWidth: number;
    originHeight: number;
    restoreWidth: number;
    restoreHeight: number;
  };

function nativeScreenBounds(
  floating: FloatingPanelLayout,
  workspace: HTMLDivElement | null,
): FloatingPanelBounds {
  if (floating.coordinateSpace === "screen" || !workspace) {
    return {
      x: floating.x,
      y: floating.y,
      width: floating.width,
      height: floating.height,
    };
  }
  const ownerWindow = workspace.ownerDocument.defaultView;
  if (!ownerWindow) {
    return { x: floating.x, y: floating.y, width: floating.width, height: floating.height };
  }
  const workspaceBounds = workspace.getBoundingClientRect();
  const sideFrame = Math.max(0, Math.round((ownerWindow.outerWidth - ownerWindow.innerWidth) / 2));
  const topFrame = Math.max(
    0,
    Math.round(ownerWindow.outerHeight - ownerWindow.innerHeight - sideFrame),
  );
  return {
    x: Math.round(ownerWindow.screenX + sideFrame + workspaceBounds.left + floating.x),
    y: Math.round(ownerWindow.screenY + topFrame + workspaceBounds.top + floating.y),
    width: floating.width,
    height: floating.height,
  };
}

function copyPanelWindowHead(source: Document, target: Document): void {
  target.head.replaceChildren();
  const charset = target.createElement("meta");
  charset.setAttribute("charset", "utf-8");
  target.head.appendChild(charset);
  source.head.querySelectorAll('style,link[rel="stylesheet"]').forEach((node) => {
    if (node.tagName === "LINK") {
      const sourceLink = node as HTMLLinkElement;
      const link = target.createElement("link");
      link.rel = "stylesheet";
      link.href = sourceLink.href;
      if (sourceLink.media) link.media = sourceLink.media;
      if (sourceLink.crossOrigin) link.crossOrigin = sourceLink.crossOrigin;
      target.head.appendChild(link);
    } else {
      target.head.appendChild(node.cloneNode(true));
    }
  });
}

/**
 * Keep one portal container for the lifetime of a panel and adopt that exact
 * node between the dock grid and a native child document. React consequently
 * preserves editors, AI conversations, and pending writes while tearing off.
 */
function StablePanelPortal({
  panelId,
  label,
  floating,
  visible,
  focused,
  suspended,
  workspaceRef,
  host,
  onExternalWindowKeyDown,
  children,
}: {
  panelId: string;
  label: string;
  floating: FloatingPanelLayout | undefined;
  visible: boolean;
  focused: boolean;
  suspended: boolean;
  workspaceRef: RefObject<HTMLDivElement>;
  host: ExternalFloatingWindowHost;
  onExternalWindowKeyDown?: (event: KeyboardEvent) => void;
  children: (external: boolean) => ReactNode;
}) {
  const inlineMountRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<Window | null>(null);
  const keyHandlerRef = useRef<((event: KeyboardEvent) => void) | null>(null);
  const externalKeyHandlerRef = useRef(onExternalWindowKeyDown);
  externalKeyHandlerRef.current = onExternalWindowKeyDown;
  const mountedRef = useRef(false);
  const [portalHost] = useState<HTMLDivElement | null>(() => (
    typeof document === "undefined" ? null : document.createElement("div")
  ));
  const [hostDocument, setHostDocument] = useState<Document>(() => (
    typeof document === "undefined" ? ({} as Document) : document
  ));
  const [external, setExternal] = useState(false);
  // Keep a live native window while it is OS-minimized. A layout restored from
  // disk with a minimized panel stays lazy until the writer restores it. Focus
  // mode is different: it temporarily suspends every external surface.
  const wantsExternal = floating !== undefined
    && !suspended
    && (visible || popupRef.current !== null);

  const moveInline = useCallback(() => {
    if (!portalHost || !inlineMountRef.current) return;
    portalHost.className = "lf-panel-portal-host";
    portalHost.removeAttribute("data-skin");
    portalHost.removeAttribute("style");
    inlineMountRef.current.appendChild(portalHost);
    setHostDocument(inlineMountRef.current.ownerDocument);
    setExternal(false);
  }, [portalHost]);

  const releasePopup = useCallback(() => {
    const popup = popupRef.current;
    if (!popup) return;
    const keyHandler = keyHandlerRef.current;
    if (keyHandler) popup.removeEventListener("keydown", keyHandler);
    keyHandlerRef.current = null;
    popupRef.current = null;
    host.release(panelId);
  }, [host, panelId]);

  useLayoutEffect(() => {
    moveInline();
  }, [moveInline]);

  useLayoutEffect(() => {
    if (!external || !portalHost) return;
    const sourceShell = workspaceRef.current?.closest<HTMLElement>(".lf-shell");
    portalHost.setAttribute("data-skin", sourceShell?.dataset.skin ?? "forge");
    const sourceStyle = sourceShell?.getAttribute("style");
    if (sourceStyle) portalHost.setAttribute("style", sourceStyle);
    portalHost.style.width = "100%";
    portalHost.style.height = "100%";
    portalHost.style.minHeight = "0";
    portalHost.style.overflow = "hidden";
  });

  useLayoutEffect(() => {
    if (!portalHost) return;
    if (!wantsExternal || !floating) {
      moveInline();
      if (popupRef.current) releasePopup();
      return;
    }
    const existing = popupRef.current;
    if (existing && !existing.closed) return;

    const popup = host.open(
      panelId,
      label,
      nativeScreenBounds(floating, workspaceRef.current),
    );
    if (!popup) {
      moveInline();
      return;
    }
    const popupDocument = popup.document;
    popupDocument.title = `LogosForge Pro — ${label}`;
    copyPanelWindowHead(workspaceRef.current?.ownerDocument ?? document, popupDocument);
    popupDocument.documentElement.className = "lf-native-panel-document";
    popupDocument.body.className = "lf-native-panel-body";
    popupDocument.body.replaceChildren();
    const sourceShell = workspaceRef.current?.closest<HTMLElement>(".lf-shell");
    portalHost.className = "lf-shell lf-native-panel-window-host";
    portalHost.setAttribute("data-skin", sourceShell?.dataset.skin ?? "forge");
    const sourceStyle = sourceShell?.getAttribute("style");
    if (sourceStyle) portalHost.setAttribute("style", sourceStyle);
    portalHost.style.width = "100%";
    portalHost.style.height = "100%";
    portalHost.style.minHeight = "0";
    portalHost.style.overflow = "hidden";
    popupDocument.body.appendChild(portalHost);
    popupRef.current = popup;
    // The listener remains attached for the popup lifetime, but resolves the
    // current callback so mode, modal, hydration and palette state never go
    // stale while the native window stays open.
    const keyHandler = (event: KeyboardEvent) => externalKeyHandlerRef.current?.(event);
    keyHandlerRef.current = keyHandler;
    popup.addEventListener("keydown", keyHandler);
    setHostDocument(popupDocument);
    setExternal(true);
    host.show(panelId, focused);
  }, [
    floating,
    focused,
    host,
    label,
    moveInline,
    onExternalWindowKeyDown,
    panelId,
    portalHost,
    releasePopup,
    wantsExternal,
    workspaceRef,
  ]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      queueMicrotask(() => {
        // React StrictMode deliberately performs a setup/cleanup/setup cycle in
        // development. A microtask lets that remount reclaim the same portal
        // before we authorize destruction of its native BrowserWindow.
        if (mountedRef.current) return;
        if (portalHost && inlineMountRef.current) inlineMountRef.current.appendChild(portalHost);
        releasePopup();
        portalHost?.remove();
      });
    };
  }, [portalHost, releasePopup]);

  if (!portalHost) return <>{children(false)}</>;
  return (
    <>
      <div ref={inlineMountRef} className="lf-panel-portal-anchor" />
      {createPortal(
        <PanelHostProvider ownerDocument={hostDocument}>
          {children(external)}
        </PanelHostProvider>,
        portalHost,
      )}
    </>
  );
}

function WorkspacePanelSurface({
  panel,
  layout,
  workspaceRef,
  viewport,
  visible,
  active,
  region,
  floating,
  disabled,
  onMove,
  onClose,
  onMoveFloating,
  onResizeFloating,
  onMinimizeFloating,
  onFocusFloating,
  externalFloatingWindows,
  onExternalWindowKeyDown,
}: {
  panel: WorkspacePanelDefinition;
  layout: WorkspaceLayout;
  workspaceRef: RefObject<HTMLDivElement>;
  viewport: WorkspaceViewport;
  visible: boolean;
  active: boolean;
  region: WorkspaceDockRegion | null;
  floating: FloatingPanelLayout | undefined;
  disabled: boolean;
  onMove: DockWorkspaceProps["onMove"];
  onClose: DockWorkspaceProps["onClose"];
  onMoveFloating: DockWorkspaceProps["onMoveFloating"];
  onResizeFloating: DockWorkspaceProps["onResizeFloating"];
  onMinimizeFloating: DockWorkspaceProps["onMinimizeFloating"];
  onFocusFloating: DockWorkspaceProps["onFocusFloating"];
  externalFloatingWindows?: ExternalFloatingWindowHost;
  onExternalWindowKeyDown?: DockWorkspaceProps["onExternalWindowKeyDown"];
}) {
  const interactionRef = useRef<FloatingInteraction | null>(null);
  const token = workspacePanelDomToken(panel.id);
  const interactionDisabled = disabled || panel.movable === false;
  const projected = floating
    ? projectFloatingBounds(floating, viewport)
    : null;
  const clearInteraction = useCallback(() => {
    interactionRef.current = null;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);
  useEffect(() => clearInteraction, [clearInteraction]);
  useEffect(() => {
    if (disabled) clearInteraction();
  }, [clearInteraction, disabled]);

  const cancelInteraction = useCallback(() => {
    const interaction = interactionRef.current;
    if (!interaction) return;
    if (interaction.kind === "move") {
      onMoveFloating(panel.id, interaction.restoreX, interaction.restoreY);
    } else {
      onResizeFloating(panel.id, interaction.restoreWidth, interaction.restoreHeight);
    }
    clearInteraction();
  }, [clearInteraction, onMoveFloating, onResizeFloating, panel.id]);

  const moveByKeyboard = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (interactionDisabled || !projected || event.target !== event.currentTarget) return;
    const step = event.shiftKey ? 48 : 12;
    let x = projected.x;
    let y = projected.y;
    if (event.key === "ArrowLeft") x -= step;
    else if (event.key === "ArrowRight") x += step;
    else if (event.key === "ArrowUp") y -= step;
    else if (event.key === "ArrowDown") y += step;
    else if (event.key === "Home") ({ x, y } = { x: 0, y: 0 });
    else return;
    event.preventDefault();
    const next = projectFloatingBounds({ ...projected, x, y }, viewport);
    onFocusFloating(panel.id);
    onMoveFloating(panel.id, next.x, next.y);
  }, [interactionDisabled, onFocusFloating, onMoveFloating, panel.id, projected, viewport]);

  const resizeByKeyboard = useCallback((event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (interactionDisabled || !projected || event.target !== event.currentTarget) return;
    const step = event.shiftKey ? 48 : 12;
    let width = projected.width;
    let height = projected.height;
    if (event.key === "ArrowLeft") width -= step;
    else if (event.key === "ArrowRight") width += step;
    else if (event.key === "ArrowUp") height -= step;
    else if (event.key === "ArrowDown") height += step;
    else if (event.key === "Home") {
      width = FLOATING_PANEL_SIZE.minWidth;
      height = FLOATING_PANEL_SIZE.minHeight;
    } else if (event.key === "End") {
      width = viewport.width > 0 ? viewport.width - projected.x : FLOATING_PANEL_SIZE.maxWidth;
      height = viewport.height > 0 ? viewport.height - projected.y : FLOATING_PANEL_SIZE.maxHeight;
    } else return;
    event.preventDefault();
    const maximumWidth = viewport.width > 0
      ? Math.max(FLOATING_PANEL_SIZE.minWidth, viewport.width - projected.x)
      : FLOATING_PANEL_SIZE.maxWidth;
    const maximumHeight = viewport.height > 0
      ? Math.max(FLOATING_PANEL_SIZE.minHeight, viewport.height - projected.y)
      : FLOATING_PANEL_SIZE.maxHeight;
    onFocusFloating(panel.id);
    if (floating?.coordinateSpace === "screen") {
      onMoveFloating(panel.id, projected.x, projected.y);
    }
    onResizeFloating(
      panel.id,
      Math.max(FLOATING_PANEL_SIZE.minWidth, Math.min(maximumWidth, Math.round(width))),
      Math.max(FLOATING_PANEL_SIZE.minHeight, Math.min(maximumHeight, Math.round(height))),
    );
  }, [floating?.coordinateSpace, interactionDisabled, onFocusFloating, onMoveFloating, onResizeFloating, panel.id, projected, viewport]);

  const dockGrid = region === "left"
    ? { gridColumn: "1", gridRow: "2" }
    : region === "center"
      ? { gridColumn: "3", gridRow: "2" }
      : region === "right"
        ? { gridColumn: "5", gridRow: "2" }
        : { gridColumn: "1 / 6", gridRow: "5" };
  const surfaceStyle = floating && projected
    ? {
      left: projected.x,
      top: projected.y,
      width: projected.width,
      height: projected.height,
      zIndex: 20 + floating.zIndex,
    }
    : dockGrid;
  const floatingActive = floating !== undefined && layout.focused?.zone === "floating"
    && layout.focused.panelId === panel.id;

  const renderSurface = (external: boolean) => (
    <section
      id={`lf-panel-${token}`}
      className={`${floating ? `lf-floating-panel${external ? " lf-native-floating-panel" : ""}` : `lf-dock-panel lf-dock-panel-${region}`}${
        floatingActive ? " lf-floating-panel-active" : ""
      }${floating?.minimized ? " lf-floating-panel-minimized" : ""}${
        panel.flush ? " lf-dock-panel-flush" : ""
      }`}
      role={floating ? "dialog" : "tabpanel"}
      aria-modal={floating ? false : undefined}
      aria-labelledby={floating ? `lf-floating-title-${token}` : `lf-tab-${token}`}
      aria-hidden={!visible}
      hidden={!visible}
      data-panel-id={panel.id}
      data-panel-active={active || undefined}
      data-panel-focused={layout.focused?.panelId === panel.id || undefined}
      data-dock-region={region ?? undefined}
      data-floating-panel={floating ? "true" : undefined}
      data-native-floating-panel={external || undefined}
      style={external ? undefined : surfaceStyle}
      onFocusCapture={() => {
        if (floating && !disabled) onFocusFloating(panel.id);
      }}
      onPointerDownCapture={() => {
        if (floating && !disabled) onFocusFloating(panel.id);
      }}
    >
      <div
        id={`lf-floating-title-${token}`}
        className="lf-floating-panel-titlebar"
        role="toolbar"
        aria-label={external
          ? `${panel.label} native window controls`
          : `Move ${panel.label} floating panel`}
        tabIndex={floating && !interactionDisabled && !external ? 0 : -1}
        hidden={!floating}
        onKeyDown={external ? undefined : moveByKeyboard}
        onPointerDown={(event) => {
          if (external || interactionDisabled || !projected) return;
          const target = event.target;
          if (target instanceof Element && target.closest("button")) return;
          onFocusFloating(panel.id);
          interactionRef.current = {
            kind: "move",
            startClientX: event.clientX,
            startClientY: event.clientY,
            originX: projected.x,
            originY: projected.y,
            restoreX: floating?.x ?? projected.x,
            restoreY: floating?.y ?? projected.y,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
          event.currentTarget.ownerDocument.body.style.cursor = "move";
          event.currentTarget.ownerDocument.body.style.userSelect = "none";
        }}
        onPointerMove={(event) => {
          const interaction = interactionRef.current;
          if (interactionDisabled || !projected || interaction?.kind !== "move") return;
          const next = projectFloatingBounds({
            ...projected,
            x: interaction.originX + event.clientX - interaction.startClientX,
            y: interaction.originY + event.clientY - interaction.startClientY,
          }, viewport);
          onMoveFloating(panel.id, next.x, next.y);
        }}
        onPointerUp={clearInteraction}
        onPointerCancel={cancelInteraction}
        onLostPointerCapture={cancelInteraction}
        title={external
          ? `${panel.label} is in a native window; use the operating-system title bar to move it between monitors`
          : `Drag ${panel.label}; arrow keys move it and Shift moves farther`}
      >
        <span className="lf-floating-panel-title">{panel.label}</span>
        <span className="lf-floating-panel-actions">
          {WORKSPACE_DOCK_REGIONS.map((destination) => (
            <button
              key={destination}
              type="button"
              disabled={!floating || interactionDisabled}
              aria-label={`Dock ${panel.label} to ${destination}`}
              title={`Dock to ${destination}`}
              onClick={() => {
                focusAfterWorkspaceAction(
                  onMove(panel.id, destination, layout.docks[destination].panelIds.length),
                  () => workspaceRef.current?.querySelector<HTMLElement>(
                    `#lf-tab-${workspacePanelDomToken(panel.id)}`,
                  ),
                );
              }}
            >
              {destination[0]!.toUpperCase()}
            </button>
          ))}
          <button
            type="button"
            disabled={!floating || interactionDisabled}
            aria-label={`Minimize ${panel.label}`}
            title={`Minimize ${panel.label}`}
            onClick={() => {
              focusAfterWorkspaceAction(
                onMinimizeFloating(panel.id, true),
                () => workspaceRef.current?.querySelector<HTMLElement>(
                  `[data-floating-restore="${token}"]`,
                ),
              );
            }}
          >
            —
          </button>
          {panel.closable !== false && (
            <button
              type="button"
              disabled={!floating || disabled}
              aria-label={`Close ${panel.label}`}
              title={`Close ${panel.label}`}
              onClick={() => {
                focusAfterWorkspaceAction(
                  onClose(panel.id),
                  () => findWorkspaceFocusControl(workspaceRef.current),
                );
              }}
            >
              ×
            </button>
          )}
        </span>
      </div>
      <div className={floating ? "lf-floating-panel-content" : "lf-dock-panel-content"}>
        {panel.node}
      </div>
      <button
        type="button"
        className="lf-floating-panel-resizer"
        aria-label={`Resize ${panel.label} floating panel`}
        aria-description={projected
          ? `${projected.width} by ${projected.height} pixels. Left and right adjust width; up and down adjust height.`
          : "Left and right adjust width; up and down adjust height."}
        tabIndex={floating && !interactionDisabled && !external ? 0 : -1}
        hidden={!floating || external}
        onKeyDown={external ? undefined : resizeByKeyboard}
        onPointerDown={(event) => {
          if (external || interactionDisabled || !projected) return;
          onFocusFloating(panel.id);
          interactionRef.current = {
            kind: "resize",
            startClientX: event.clientX,
            startClientY: event.clientY,
            originWidth: projected.width,
            originHeight: projected.height,
            restoreWidth: floating?.width ?? projected.width,
            restoreHeight: floating?.height ?? projected.height,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
          event.currentTarget.ownerDocument.body.style.cursor = "nwse-resize";
          event.currentTarget.ownerDocument.body.style.userSelect = "none";
        }}
        onPointerMove={(event) => {
          const interaction = interactionRef.current;
          if (interactionDisabled || !projected || interaction?.kind !== "resize") return;
          const maximumWidth = viewport.width > 0
            ? Math.max(FLOATING_PANEL_SIZE.minWidth, viewport.width - projected.x)
            : FLOATING_PANEL_SIZE.maxWidth;
          const maximumHeight = viewport.height > 0
            ? Math.max(FLOATING_PANEL_SIZE.minHeight, viewport.height - projected.y)
            : FLOATING_PANEL_SIZE.maxHeight;
          if (floating?.coordinateSpace === "screen") {
            onMoveFloating(panel.id, projected.x, projected.y);
          }
          onResizeFloating(
            panel.id,
            Math.max(FLOATING_PANEL_SIZE.minWidth, Math.min(
              maximumWidth,
              interaction.originWidth + event.clientX - interaction.startClientX,
            )),
            Math.max(FLOATING_PANEL_SIZE.minHeight, Math.min(
              maximumHeight,
              interaction.originHeight + event.clientY - interaction.startClientY,
            )),
          );
        }}
        onPointerUp={clearInteraction}
        onPointerCancel={cancelInteraction}
        onLostPointerCapture={cancelInteraction}
        title={`Drag to resize ${panel.label}; arrow keys also work`}
      />
    </section>
  );

  if (externalFloatingWindows) {
    return (
      <StablePanelPortal
        panelId={panel.id}
        label={panel.label}
        floating={floating}
        visible={visible}
        focused={floatingActive}
        suspended={layout.preset === "focus"}
        workspaceRef={workspaceRef}
        host={externalFloatingWindows}
        onExternalWindowKeyDown={onExternalWindowKeyDown}
      >
        {renderSurface}
      </StablePanelPortal>
    );
  }
  return renderSurface(false);
}

/**
 * A four-region work surface whose panel wrappers always remain children of
 * one stable React parent. Moving a tab changes its CSS grid coordinates; it
 * does not reparent/remount editors, chat sessions, or their pending state.
 */
export function DockWorkspace({
  layout,
  panels,
  disabled = false,
  onActivate,
  onMove,
  onFloat,
  onClose,
  onToggleDock,
  onResizeDock,
  onMoveFloating,
  onResizeFloating,
  onMinimizeFloating,
  onFocusFloating,
  onReset,
  externalFloatingWindows,
  onExternalWindowKeyDown,
}: DockWorkspaceProps) {
  const workspaceRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState<WorkspaceViewport>({ width: 0, height: 0 });
  const [floatingDropActive, setFloatingDropActive] = useState(false);
  const panelById = useMemo(() => new Map(panels.map((panel) => [panel.id, panel])), [panels]);
  const visibility = getWorkspaceVisibility(layout);
  const focus = layout.preset === "focus";
  const leftHasPanels = layout.docks.left.panelIds.length > 0;
  const rightHasPanels = layout.docks.right.panelIds.length > 0;
  const bottomHasPanels = layout.docks.bottom.panelIds.length > 0;
  const leftVisible = visibility.docks.left;
  const rightVisible = visibility.docks.right;
  const bottomVisible = visibility.docks.bottom;
  const leftExtent = focus || !leftHasPanels ? 0 : leftVisible ? layout.docks.left.sizePx : COLLAPSED_DOCK_PX;
  const rightExtent = focus || !rightHasPanels ? 0 : rightVisible ? layout.docks.right.sizePx : COLLAPSED_DOCK_PX;
  const bottomHeaderExtent = focus || !bottomHasPanels ? 0 : bottomVisible ? 34 : 28;
  const bottomBodyExtent = bottomVisible ? layout.docks.bottom.sizePx : 0;
  const leftSeparator = leftVisible ? DOCK_SEPARATOR_PX : 0;
  const rightSeparator = rightVisible ? DOCK_SEPARATOR_PX : 0;

  useLayoutEffect(() => {
    const root = workspaceRef.current;
    if (!root) return;
    const update = () => {
      const bounds = root.getBoundingClientRect();
      const next = { width: Math.round(bounds.width), height: Math.round(bounds.height) };
      setViewport((current) => current.width === next.width && current.height === next.height
        ? current
        : next);
    };
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(root);
    return () => observer.disconnect();
  }, []);

  // Project both preferred side sizes together. Persisted sizes stay untouched,
  // while the live grid always reserves a readable center track.
  let leftTrackPx = leftExtent;
  let rightTrackPx = rightExtent;
  if (viewport.width > 0) {
    const available = Math.max(
      0,
      viewport.width - MIN_CENTER_WIDTH_PX - leftSeparator - rightSeparator,
    );
    if (leftTrackPx + rightTrackPx > available) {
      if (!leftVisible && rightVisible) {
        leftTrackPx = Math.min(leftTrackPx, available);
        rightTrackPx = Math.max(0, available - leftTrackPx);
      } else if (leftVisible && !rightVisible) {
        rightTrackPx = Math.min(rightTrackPx, available);
        leftTrackPx = Math.max(0, available - rightTrackPx);
      } else {
        const desired = leftTrackPx + rightTrackPx;
        const ratio = desired <= 0 ? 0.5 : leftTrackPx / desired;
        leftTrackPx = Math.round(available * ratio);
        rightTrackPx = Math.max(0, available - leftTrackPx);
      }
    }
  }
  // Persist the writer's preferred sizes, but project them through soft center
  // minimums at render time. A maximized navigator plus a maximized right or
  // bottom dock must never squeeze the manuscript track to zero.
  const bottomTrack = bottomVisible
    ? `min(${bottomBodyExtent}px, max(0px, calc(100% - ${
      DOCK_HEADER_PX + DOCK_SEPARATOR_PX + DOCK_HEADER_PX + MIN_CENTER_HEIGHT_PX
    }px)))`
    : "0px";

  const rootStyle = {
    gridTemplateColumns: `${leftTrackPx}px ${leftSeparator}px minmax(0, 1fr) ${rightSeparator}px ${rightTrackPx}px`,
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
      onDragOver={(event) => {
        if (disabled || !event.dataTransfer.types.includes(DRAG_MIME)) return;
        event.preventDefault();
        setFloatingDropActive(true);
      }}
      onDragLeave={(event) => {
        const related = event.relatedTarget;
        if (!(related instanceof Node) || !event.currentTarget.contains(related)) {
          setFloatingDropActive(false);
        }
      }}
      onDragEndCapture={() => setFloatingDropActive(false)}
      onDrop={(event) => {
        if (disabled) return;
        const panelId = event.dataTransfer.getData(DRAG_MIME)
          || event.dataTransfer.getData("text/plain");
        setFloatingDropActive(false);
        if (!panelId || panelById.get(panelId)?.movable === false) return;
        event.preventDefault();
        const bounds = event.currentTarget.getBoundingClientRect();
        focusAfterWorkspaceAction(
          onFloat(panelId, {
            x: event.clientX - bounds.left - 80,
            y: event.clientY - bounds.top - 16,
          }),
          () => workspaceRef.current?.querySelector<HTMLElement>(
            `#lf-floating-title-${workspacePanelDomToken(panelId)}`,
          ),
        );
      }}
    >
      {leftVisible && (
        <DockHeader
          region="left"
          layout={layout}
          workspaceRef={workspaceRef}
          panelById={panelById}
          disabled={disabled}
          onActivate={onActivate}
          onMove={onMove}
          onFloat={onFloat}
          onClose={onClose}
          onToggleDock={onToggleDock}
          onReset={onReset}
        />
      )}
      <DockHeader
        region="center"
        layout={layout}
        workspaceRef={workspaceRef}
        panelById={panelById}
        disabled={disabled}
        onActivate={onActivate}
        onMove={onMove}
        onFloat={onFloat}
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
          onFloat={onFloat}
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
          onFloat={onFloat}
          onClose={onClose}
          onToggleDock={onToggleDock}
          onReset={onReset}
        />
      )}

      {leftVisible && (
        <DockResizer
          region="left"
          value={layout.docks.left.sizePx}
          workspaceRef={workspaceRef}
          oppositeExtent={rightTrackPx}
          disabled={disabled}
          onChange={(value) => onResizeDock("left", value)}
        />
      )}
      {rightVisible && (
        <DockResizer
          region="right"
          value={layout.docks.right.sizePx}
          workspaceRef={workspaceRef}
          oppositeExtent={leftTrackPx}
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

      {!focus && leftHasPanels && !leftVisible && (
        <button
          type="button"
          className="lf-dock-collapsed lf-dock-collapsed-left"
          disabled={disabled}
          onClick={() => {
            focusAfterWorkspaceAction(
              onToggleDock("left"),
              () => workspaceRef.current?.querySelector<HTMLElement>(
                '[data-dock-drop-region="left"] [role="tab"][aria-selected="true"]',
              ),
            );
          }}
          aria-label="Expand left dock"
        >
          LEFT ›
        </button>
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
          const placement = getPanelPlacement(layout, panel.id);
          if (placement === null) return null;
          // Focus is a visual projection, not a layout mutation. Manuscript is
          // rendered full-center while its real dock/floating placement remains
          // byte-for-byte available for the return to Cockpit.
          const focusProjection = focus && panel.id === "manuscript";
          const region = focusProjection
            ? "center"
            : placement.kind === "dock" ? placement.region : null;
          const floating = !focusProjection && placement.kind === "floating"
            ? layout.floatingPanels.find((entry) => entry.panelId === panel.id)
            : undefined;
          const active = focusProjection
            ? true
            : region === null
            ? layout.focused?.zone === "floating" && layout.focused.panelId === panel.id
            : layout.docks[region].activePanelId === panel.id;
          const visible = focusProjection
            ? true
            : floating
            ? visibility.floatingPanelIds.includes(panel.id)
            : region !== null && active && visibility.docks[region];
          return (
            <WorkspacePanelSurface
              key={panel.id}
              panel={panel}
              layout={layout}
              workspaceRef={workspaceRef}
              viewport={viewport}
              visible={visible}
              active={active}
              region={region}
              floating={floating}
              disabled={disabled}
              onMove={onMove}
              onClose={onClose}
              onMoveFloating={onMoveFloating}
              onResizeFloating={onResizeFloating}
              onMinimizeFloating={onMinimizeFloating}
              onFocusFloating={onFocusFloating}
              externalFloatingWindows={externalFloatingWindows}
              onExternalWindowKeyDown={onExternalWindowKeyDown}
            />
          );
        })}
      </div>
      {!focus && layout.floatingPanels.some((panel) => panel.minimized) && (
        <div className="lf-floating-minimized-tray" role="toolbar" aria-label="Minimized panels">
          <span className="lf-floating-minimized-tray-label">FLOATS</span>
          {layout.floatingPanels.filter((entry) => entry.minimized).map((entry) => {
            const panel = panelById.get(entry.panelId);
            if (!panel) return null;
            const token = workspacePanelDomToken(panel.id);
            return (
              <button
                key={panel.id}
                type="button"
                className="lf-floating-minimized-tray-item"
                data-floating-restore={token}
                disabled={disabled}
                aria-label={`Restore ${panel.label}`}
                onClick={() => {
                  focusAfterWorkspaceAction(
                    onMinimizeFloating(panel.id, false),
                    () => workspaceRef.current?.querySelector<HTMLElement>(
                      `#lf-floating-title-${token}`,
                    ),
                  );
                }}
              >
                {panel.label}
              </button>
            );
          })}
        </div>
      )}
      <div
        className={`lf-dock-drop-target lf-dock-drop-target-floating${floatingDropActive ? " is-active" : ""}`}
        data-drop-active={floatingDropActive || undefined}
        aria-hidden="true"
      />
    </div>
  );
}
