import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ModalDialogHarness } from "./ModalDialogHarness";
import { ErrorBoundaryHarness } from "./ErrorBoundaryHarness";
import { RuntimeFaultHarness } from "./RuntimeFaultHarness";
import { LifecycleHarness } from "./LifecycleHarness";
import { LargeManuscriptHarness } from "./LargeManuscriptHarness";
import { WorkspaceDockHarness } from "./WorkspaceDockHarness";

const query = new URLSearchParams(window.location.search);
const content = query.has("modal-harness")
  ? <ModalDialogHarness />
  : query.has("error-boundary-harness")
    ? <ErrorBoundaryHarness />
    : query.has("runtime-fault-harness")
      ? <RuntimeFaultHarness />
      : query.has("lifecycle-harness")
        ? <LifecycleHarness />
        : query.has("large-manuscript-harness")
          ? <LargeManuscriptHarness />
          : query.has("workspace-dock-harness")
            ? <WorkspaceDockHarness />
    : <App />;

createRoot(document.getElementById("root")!).render(content);
