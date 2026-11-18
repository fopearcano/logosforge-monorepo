import { useMemo, useState, type CSSProperties } from "react";
import { Corners, PanelShell, type PanelProps } from "../../components/shell/PanelShell";
import { useProCloudSync } from "./ProCloudSyncProvider";
import { newestCloudHead } from "./model";

const panelBox: CSSProperties = {
  position: "relative", width: "100%", height: "100%", overflow: "hidden",
  display: "flex", flexDirection: "column",
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)", boxShadow: "var(--page-shadow)",
};

const buttonStyle: CSSProperties = {
  border: "1px solid var(--line-cy,var(--line2))", background: "var(--tint)",
  color: "var(--strong)", font: "inherit", fontSize: 9, letterSpacing: ".08em",
  padding: "6px 10px", cursor: "pointer",
};

function timeLabel(value: string | null): string {
  if (!value) return "never";
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleString() : "unknown";
}
function ConfirmAction({
  label, confirmLabel, disabled, onConfirm,
}: {
  label: string;
  confirmLabel: string;
  disabled: boolean;
  onConfirm: () => Promise<void>;
}) {
  const [armed, setArmed] = useState(false);
  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={armed ? confirmLabel : label}
      onBlur={() => setArmed(false)}
      onClick={() => {
        if (!armed) { setArmed(true); return; }
        setArmed(false);
        void onConfirm();
      }}
      style={{ ...buttonStyle, color: armed ? "var(--blocking)" : "var(--strong)", opacity: disabled ? 0.45 : 1 }}
    >
      {armed ? confirmLabel : label}
    </button>
  );
}

export function CloudSyncPanel(props: PanelProps) {
  const { state, actions } = useProCloudSync();
  const native = state.native;
  const boundCloudIds = useMemo(
    () => new Set(native?.bindings.map((binding) => binding.cloudProjectId) ?? []),
    [native?.bindings],
  );
  const remoteProjects = native?.projects.filter((project) => (
    !boundCloudIds.has(project.cloudProjectId)
    && !native.ignoredCloudProjectIds.includes(project.cloudProjectId)
  )) ?? [];
  const recoveredBranches = native?.recoveredRemoteHeads.flatMap((entry) => {
    const project = native.projects.find((candidate) => candidate.cloudProjectId === entry.cloudProjectId);
    return entry.snapshotIds.map((snapshotId) => ({
      cloudProjectId: entry.cloudProjectId,
      snapshotId,
      projectTitle: project?.title ?? "Cloud project",
      snapshot: project?.snapshots.find((candidate) => candidate.snapshotId === snapshotId) ?? null,
    }));
  }) ?? [];
  const statusColor = state.status === "up-to-date"
    ? "var(--green)"
    : state.status === "attention" || state.status === "checking"
      ? "var(--amber-b,#ffb454)"
      : state.status === "error" ? "var(--blocking)" : "var(--txt3)";

  return (
    <PanelShell {...props}>
      <div data-screen-label="Cloud Sync" style={panelBox}>
        <Corners />
        <div style={{ height: 44, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "var(--display-font)", fontWeight: 600, fontSize: 13, letterSpacing: ".14em", color: "var(--strong)" }}>CLOUD FOLDER SYNC</span>
          <span role="status" aria-live="polite" style={{ fontSize: 8, color: statusColor, letterSpacing: ".12em" }}>● {state.status.toUpperCase()}</span>
          <span style={{ flex: 1 }} />
          {native?.enabled && (
            <button type="button" disabled={state.busy} onClick={() => { void actions.syncNow(); }} style={{ ...buttonStyle, opacity: state.busy ? 0.45 : 1 }}>
              {state.busy ? "WORKING…" : "SYNC NOW"}
            </button>
          )}
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px 28px" }}>
          <div role={state.status === "error" ? "alert" : "status"} style={{ border: `1px solid ${statusColor}`, background: "var(--tint)", padding: "10px 12px", color: "var(--txt2)", fontSize: 10.5, lineHeight: 1.55 }}>
            {state.detail}
          </div>

          {!state.available ? (
            <div style={{ marginTop: 18, color: "var(--txt2)", fontSize: 11, lineHeight: 1.65 }}>
              Open this project in the packaged desktop app to link a local folder managed by Google Drive, Dropbox, OneDrive, iCloud Drive or Syncthing.
            </div>
          ) : (
            <>
              <section aria-labelledby="cloud-folder-heading" style={{ marginTop: 18 }}>
                <div id="cloud-folder-heading" style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".16em", marginBottom: 7 }}>PROVIDER FOLDER</div>
                <div style={{ border: "1px solid var(--line2)", background: "var(--panel2)", padding: 12 }}>
                  <div style={{ fontSize: 10, color: "var(--strong)", overflowWrap: "anywhere" }}>{native?.folderPath ?? "No folder selected"}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
                    <button type="button" disabled={state.busy} onClick={() => { void actions.chooseFolder(); }} style={buttonStyle}>
                      {native?.enabled ? "CHANGE FOLDER" : "CHOOSE FOLDER"}
                    </button>
                    {native?.enabled && <button type="button" disabled={state.busy} onClick={() => { void actions.disable(); }} style={buttonStyle}>DISABLE</button>}
                  </div>
                  <p style={{ margin: "10px 0 0", color: "var(--txt3)", fontSize: 9, lineHeight: 1.55 }}>
                    LogosForge stores provider-neutral snapshot files only. Your installed cloud app moves them; LogosForge never asks for a Google, Dropbox or Microsoft password or token. At-rest encryption, when enabled, is controlled by the provider or your disk.
                  </p>
                  <p style={{ margin: "6px 0 0", color: "var(--txt3)", fontSize: 8.5, lineHeight: 1.5 }}>
                    Use a locally available or mirrored provider folder. If a streaming-only placeholder cannot make an atomic immutable file, the snapshot stays safely queued; make the folder available offline or choose another folder.
                  </p>
                </div>
              </section>

              {native?.enabled && (
                <section aria-labelledby="cloud-automatic-heading" style={{ marginTop: 18 }}>
                  <div id="cloud-automatic-heading" style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".16em", marginBottom: 7 }}>AUTOMATIC SYNC · BETA</div>
                  <label style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--txt2)", fontSize: 10.5 }}>
                    <input
                      type="checkbox"
                      checked={native.automatic}
                      disabled={state.busy}
                      onChange={(event) => { void actions.setAutomatic(event.currentTarget.checked); }}
                    />
                    Compare and publish complete project snapshots every 10 minutes
                  </label>
                  <div style={{ marginTop: 7, fontSize: 9, color: "var(--txt3)" }}>
                    Last delivered: {timeLabel(native.lastSuccessfulSyncAt)} · queued: {native.outboxCount}
                    {native.outboxCount > 0 && (
                      <button type="button" disabled={state.busy} onClick={() => { void actions.retryOutbox(); }} style={{ ...buttonStyle, marginLeft: 9, padding: "3px 7px" }}>RETRY DELIVERY</button>
                    )}
                  </div>
                  <p style={{ margin: "8px 0 0", color: "var(--txt3)", fontSize: 8.5, lineHeight: 1.5 }}>
                    Sync Now remains immediate. Each changed publish is an immutable recovery version and consumes provider storage; LogosForge does not silently delete that history.
                  </p>
                </section>
              )}

              {state.review && (
                <section aria-labelledby="cloud-conflict-heading" style={{ marginTop: 18, border: "1px solid var(--amber-b,#ffb454)", background: "color-mix(in srgb,var(--amber-b,#ffb454) 7%,var(--panel2))", padding: 12 }}>
                  <div id="cloud-conflict-heading" style={{ fontFamily: "var(--display-font)", color: "var(--amber-b,#ffb454)", fontSize: 11, letterSpacing: ".1em" }}>REVIEW PRESERVED COPIES</div>
                  <p style={{ color: "var(--txt2)", fontSize: 10, lineHeight: 1.55 }}>{state.review.reason}</p>
                  {state.review.heads.length > 0 ? (
                    <>
                      <div style={{ fontSize: 9, color: "var(--txt3)", marginBottom: 10 }}>
                        {state.review.heads.length} cloud head{state.review.heads.length === 1 ? "" : "s"} · newest {timeLabel(newestCloudHead(state.review.heads)?.createdAt ?? null)}
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        <button type="button" disabled={state.busy} onClick={() => { void actions.keepBoth(); }} style={buttonStyle}>KEEP BOTH</button>
                        <ConfirmAction label="USE CLOUD COPY" confirmLabel="CONFIRM USE CLOUD" disabled={state.busy} onConfirm={actions.useCloudCopy} />
                        <ConfirmAction label="REPLACE CLOUD" confirmLabel="CONFIRM REPLACE CLOUD" disabled={state.busy} onConfirm={actions.replaceCloudCopy} />
                      </div>
                      <p style={{ margin: "9px 0 0", fontSize: 8.5, color: "var(--txt3)", lineHeight: 1.5 }}>
                        Keep Both imports the newest cloud copy as a separate local project, then preserves this local copy as the continuing cloud head. The other choices require a second click.
                      </p>
                    </>
                  ) : (
                    <div>
                      <p style={{ fontSize: 9, color: "var(--txt3)" }}>The linked remote history is absent or invalid; it will not be recreated silently.</p>
                      <ConfirmAction label="FORGET BROKEN LINK" confirmLabel="CONFIRM FORGET LINK" disabled={state.busy} onConfirm={actions.forgetActiveBinding} />
                    </div>
                  )}
                </section>
              )}

              {remoteProjects.length > 0 && (
                <section aria-labelledby="cloud-discovery-heading" style={{ marginTop: 18 }}>
                  <div id="cloud-discovery-heading" style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".16em", marginBottom: 7 }}>OTHER DEVICE PROJECTS</div>
                  <div style={{ display: "grid", gap: 8 }}>
                    {remoteProjects.map((project) => (
                      <div key={project.cloudProjectId} style={{ display: "flex", gap: 10, alignItems: "center", border: "1px solid var(--line2)", background: "var(--panel2)", padding: 10 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ color: "var(--strong)", fontSize: 10.5 }}>{project.title || "Untitled project"}</div>
                          <div style={{ color: "var(--txt3)", fontSize: 8.5, marginTop: 3 }}>{project.headSnapshotIds.length} preserved head{project.headSnapshotIds.length === 1 ? "" : "s"}</div>
                        </div>
                        <button type="button" disabled={state.busy} onClick={() => { void actions.importRemote(project.cloudProjectId); }} style={buttonStyle}>IMPORT</button>
                        <button type="button" disabled={state.busy} aria-label={`Ignore ${project.title || "remote project"}`} onClick={() => { void actions.ignoreRemote(project.cloudProjectId); }} style={buttonStyle}>IGNORE</button>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {recoveredBranches.length > 0 && (
                <section aria-labelledby="cloud-preserved-heading" style={{ marginTop: 18 }}>
                  <div id="cloud-preserved-heading" style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".16em", marginBottom: 7 }}>PRESERVED PROVIDER BRANCHES</div>
                  <p style={{ margin: "0 0 9px", color: "var(--txt3)", fontSize: 9, lineHeight: 1.5 }}>
                    These heads were superseded during conflict recovery but remain immutable and can be restored as separate local projects.
                  </p>
                  <div style={{ display: "grid", gap: 8 }}>
                    {recoveredBranches.map((branch) => (
                      <div key={`${branch.cloudProjectId}:${branch.snapshotId}`} style={{ display: "flex", gap: 10, alignItems: "center", border: "1px solid var(--line2)", background: "var(--panel2)", padding: 10 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ color: "var(--strong)", fontSize: 10.5 }}>{branch.projectTitle}</div>
                          <div style={{ color: "var(--txt3)", fontSize: 8.5, marginTop: 3 }}>
                            {branch.snapshot ? `preserved ${timeLabel(branch.snapshot.createdAt)}` : "snapshot file unavailable"}
                          </div>
                        </div>
                        <button
                          type="button"
                          disabled={state.busy || !branch.snapshot}
                          onClick={() => { void actions.recoverRemoteHead(branch.cloudProjectId, branch.snapshotId); }}
                          style={{ ...buttonStyle, opacity: state.busy || !branch.snapshot ? 0.45 : 1 }}
                        >
                          RECOVER COPY
                        </button>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {native && (native.warnings.length > 0 || native.actionReceipts.length > 0) && (
                <section aria-labelledby="cloud-recovery-heading" style={{ marginTop: 18 }}>
                  <div id="cloud-recovery-heading" style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".16em", marginBottom: 7 }}>RECOVERY LOG</div>
                  {native.warnings.map((warning, index) => <div key={`${warning}:${index}`} style={{ color: "var(--amber-b,#ffb454)", fontSize: 9, lineHeight: 1.5 }}>{warning}</div>)}
                  {native.actionReceipts.length > 0 && <div style={{ color: "var(--txt2)", fontSize: 9, lineHeight: 1.5 }}>{native.actionReceipts.length} interrupted recovery action{native.actionReceipts.length === 1 ? " is" : "s are"} retained for safe retry.</div>}
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </PanelShell>
  );
}

