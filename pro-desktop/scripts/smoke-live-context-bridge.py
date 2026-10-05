"""Exercise CoreManager -> FastAPI -> connector/MCP live context end to end."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import signal
import socket
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import mcp
from mcp.client.stdio import stdio_client

_DRIVER_PREFIX = "@@LOGOSFORGE_LIVE_CONTEXT_DRIVER@@"


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _api_json(
    base_url: str,
    token: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not path.startswith("/api/"):
        raise RuntimeError(f"unsafe API path: {path}")
    encoded = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=encoded,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if encoded is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"API {method} {path} failed with HTTP {exc.code}: {detail[:1000]}"
        ) from None
    if not isinstance(result, dict):
        raise TypeError(f"API {method} {path} returned a non-object response")
    return result


def _connector(
    base_url: str,
    token: str,
    project_id: int,
    action: str,
) -> dict[str, Any]:
    return _api_json(
        base_url,
        token,
        "POST",
        f"/api/projects/{project_id}/connector/execute",
        {"action": action, "args": {}},
    )


class _Driver:
    def __init__(
        self,
        *,
        node: str,
        script: Path,
        manager: Path,
        core: Path,
        db: Path,
        descriptor: Path,
        port: int,
    ) -> None:
        env = os.environ.copy()
        env["LOGOSFORGE_PORT"] = str(port)
        command = [
            node,
            str(script),
            "--manager",
            str(manager),
            "--core",
            str(core),
            "--db",
            str(db),
            "--descriptor",
            str(descriptor),
        ]
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._deferred: list[dict[str, Any]] = []
        self._logs: list[str] = []
        self._next_id = 1
        self._stopped = False
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.process = subprocess.Popen(
            command,
            cwd=script.parent,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        assert self.process.stdout is not None
        for raw_line in self.process.stdout:
            line = raw_line.rstrip("\r\n")
            if line.startswith(_DRIVER_PREFIX):
                try:
                    message = json.loads(line[len(_DRIVER_PREFIX):])
                except json.JSONDecodeError:
                    self._logs.append(line)
                    continue
                if isinstance(message, dict):
                    self._messages.put(message)
                    continue
            self._logs.append(line)
            if len(self._logs) > 200:
                del self._logs[:-200]
        self._messages.put({"event": "eof", "returncode": self.process.poll()})

    def _wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        for index, message in enumerate(self._deferred):
            if predicate(message):
                return self._deferred.pop(index)
        while True:
            try:
                message = self._messages.get(timeout=timeout)
            except queue.Empty:
                tail = "\n".join(self._logs[-30:])
                raise RuntimeError(f"CoreManager driver timed out.\n{tail}") from None
            if message.get("event") == "fatal":
                raise RuntimeError(f"CoreManager driver failed: {message.get('error')}")
            if message.get("event") == "eof":
                tail = "\n".join(self._logs[-30:])
                raise RuntimeError(
                    "CoreManager driver exited unexpectedly "
                    f"({message.get('returncode')}).\n{tail}"
                )
            if predicate(message):
                return message
            self._deferred.append(message)

    def wait_ready(self, timeout: float = 60) -> dict[str, Any]:
        return self._wait_for(
            lambda message: message.get("event") == "ready",
            timeout=timeout,
        )

    def command(self, command: str, **payload: Any) -> None:
        if self.process.poll() is not None:
            raise RuntimeError("CoreManager driver is no longer running")
        request_id = self._next_id
        self._next_id += 1
        request = {"id": request_id, "command": command, **payload}
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        response = self._wait_for(
            lambda message: message.get("id") == request_id,
            timeout=30,
        )
        if response.get("ok") is not True:
            raise RuntimeError(
                f"CoreManager driver command {command!r} failed: "
                f"{response.get('error')}"
            )
        if command == "stop":
            self._stopped = True

    def close(self) -> None:
        if self.process.poll() is None and not self._stopped:
            try:
                self.command("stop")
            except (OSError, RuntimeError) as exc:
                self._logs.append(f"driver cleanup warning: {exc}")
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=12)
            return
        except subprocess.TimeoutExpired:
            pass
        if os.name == "nt":
            subprocess.run(
                ["taskkill.exe", "/PID", str(self.process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.process.wait(timeout=5)


def _structured(result: Any, label: str) -> dict[str, Any]:
    if result.isError:
        raise RuntimeError(f"{label} failed")
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if not isinstance(structured, dict) or structured.get("ok") is not True:
        raise RuntimeError(f"{label} returned an invalid structured envelope")
    payload = structured.get("result")
    if not isinstance(payload, dict):
        raise TypeError(f"{label} returned a non-object result")
    return payload


def _assert_published(
    live: dict[str, Any],
    selection: dict[str, Any],
    scene: dict[str, Any],
    *,
    project_id: int,
    scene_id: int,
    expected_selection: str,
) -> int:
    if not (
        live.get("available") is True
        and live.get("project_id") == project_id
        and live.get("active_panel_id") == "manuscript"
        and live.get("active_scene_id") == scene_id
        and live.get("selection_section") == "Manuscript"
        and live.get("selection_length") == len(expected_selection)
    ):
        raise RuntimeError(f"live context did not match publication: {live!r}")
    revision = live.get("revision")
    if type(revision) is not int or revision < 1:
        raise RuntimeError(f"live context returned an invalid revision: {revision!r}")
    if not (
        selection.get("available") is True
        and selection.get("selection") == expected_selection
        and selection.get("length") == len(expected_selection)
        and selection.get("revision") == revision
    ):
        raise RuntimeError(f"current selection did not match publication: {selection!r}")
    if scene.get("id") != scene_id or scene.get("title") != "Opening":
        raise RuntimeError(f"current scene did not match publication: {scene!r}")
    return revision


def _assert_cleared(
    live: dict[str, Any],
    selection: dict[str, Any],
    scene_envelope: dict[str, Any],
) -> None:
    if not (
        live.get("available") is False
        and live.get("project_id") is None
        and live.get("revision") is None
    ):
        raise RuntimeError(f"cleared live context remained available: {live!r}")
    if not (
        selection.get("available") is False
        and selection.get("selection") == ""
        and selection.get("length") == 0
        and selection.get("revision") is None
    ):
        raise RuntimeError(f"cleared selection remained available: {selection!r}")
    if scene_envelope.get("ok") is not False or "active scene" not in str(
        scene_envelope.get("error", "")
    ).lower():
        raise RuntimeError(
            f"cleared active scene did not fail closed: {scene_envelope!r}"
        )


async def _exercise_mcp(
    *,
    driver: _Driver,
    mcp_executable: Path,
    descriptor: Path,
    base_url: str,
    auth_token: str,
    project_id: int,
    scene_id: int,
    selection: str,
) -> None:
    env = os.environ.copy()
    for name in ("LOGOSFORGE_API_URL", "LOGOSFORGE_API_TOKEN"):
        env.pop(name, None)
    env.update(
        {
            "LOGOSFORGE_MCP_CONNECTION_FILE": str(descriptor),
            "LOGOSFORGE_MCP_REQUIRE_CONNECTION": "1",
            "LOGOSFORGE_MCP_ALLOW_WRITES": "0",
        }
    )
    params = mcp.StdioServerParameters(
        command=str(mcp_executable),
        args=[],
        cwd=str(mcp_executable.parent),
        env=env,
    )
    async with (
        stdio_client(params) as streams,
        mcp.ClientSession(*streams) as session,
    ):
        initialized = await session.initialize()
        if initialized.serverInfo.name != "logosforge":
            raise RuntimeError(f"unexpected MCP server: {initialized.serverInfo.name!r}")
        _structured(
            await session.call_tool(
                "logosforge_select_project", {"project_id": project_id}
            ),
            "MCP project selection",
        )

        mcp_live = _structured(
            await session.call_tool("logosforge_get_live_context", {}),
            "MCP live-context read",
        )
        mcp_selection = _structured(
            await session.call_tool("logosforge_get_current_selection", {}),
            "MCP selection read",
        )
        mcp_scene = _structured(
            await session.call_tool("logosforge_get_current_scene", {}),
            "MCP active-scene read",
        )
        first_revision = _assert_published(
            mcp_live,
            mcp_selection,
            mcp_scene,
            project_id=project_id,
            scene_id=scene_id,
            expected_selection=selection,
        )

        await asyncio.to_thread(driver.command, "suspend")
        await asyncio.to_thread(
            driver.command,
            "publish",
            context={
                "projectId": project_id,
                "activePanelId": "outline",
                "activeSceneId": scene_id,
                "selectionSection": "Outline",
                "selection": "must not resurrect after suspension",
            },
        )

        connector_live = _connector(
            base_url, auth_token, project_id, "get_live_context"
        )
        connector_selection = _connector(
            base_url, auth_token, project_id, "get_current_selection"
        )
        connector_scene = _connector(
            base_url, auth_token, project_id, "get_active_scene"
        )
        if connector_live.get("ok") is not True:
            raise RuntimeError(f"connector live-context clear read failed: {connector_live!r}")
        if connector_selection.get("ok") is not True:
            raise RuntimeError(f"connector selection clear read failed: {connector_selection!r}")
        _assert_cleared(
            connector_live.get("result") or {},
            connector_selection.get("result") or {},
            connector_scene,
        )

        cleared_live_result = await session.call_tool(
            "logosforge_get_live_context", {}
        )
        cleared_selection_result = await session.call_tool(
            "logosforge_get_current_selection", {}
        )
        cleared_scene_result = await session.call_tool(
            "logosforge_get_current_scene", {}
        )
        cleared_live = _structured(cleared_live_result, "cleared MCP live-context read")
        cleared_selection = _structured(
            cleared_selection_result, "cleared MCP selection read"
        )
        cleared_scene_envelope = getattr(
            cleared_scene_result, "structuredContent", None
        )
        if cleared_scene_envelope is None:
            cleared_scene_envelope = getattr(
                cleared_scene_result, "structured_content", None
            )
        if cleared_scene_result.isError is not True or not isinstance(
            cleared_scene_envelope, dict
        ):
            raise RuntimeError("cleared MCP active-scene read did not fail closed")
        _assert_cleared(
            cleared_live,
            cleared_selection,
            cleared_scene_envelope,
        )

        resumed_selection = "resumed live-context selection"
        await asyncio.to_thread(driver.command, "resume")
        await asyncio.to_thread(
            driver.command,
            "publish",
            context={
                "projectId": project_id,
                "activePanelId": "manuscript",
                "activeSceneId": scene_id,
                "selectionSection": "Manuscript",
                "selection": resumed_selection,
            },
        )
        resumed_live = _structured(
            await session.call_tool("logosforge_get_live_context", {}),
            "resumed MCP live-context read",
        )
        resumed_selection_result = _structured(
            await session.call_tool("logosforge_get_current_selection", {}),
            "resumed MCP selection read",
        )
        resumed_scene = _structured(
            await session.call_tool("logosforge_get_current_scene", {}),
            "resumed MCP active-scene read",
        )
        resumed_revision = _assert_published(
            resumed_live,
            resumed_selection_result,
            resumed_scene,
            project_id=project_id,
            scene_id=scene_id,
            expected_selection=resumed_selection,
        )
        if resumed_revision <= first_revision:
            raise RuntimeError(
                "resumed publication did not advance the ordered revision"
            )

        canvas_selection = "Canvas Plot node selected through CoreManager"
        await asyncio.to_thread(
            driver.command,
            "publish",
            context={
                "projectId": project_id,
                "activePanelId": "canvas-plot",
                "activeSceneId": None,
                "selectionSection": "Canvas Plot",
                "selection": canvas_selection,
            },
        )
        canvas_live = _structured(
            await session.call_tool("logosforge_get_live_context", {}),
            "Canvas Plot MCP live-context read",
        )
        canvas_selection_result = _structured(
            await session.call_tool("logosforge_get_current_selection", {}),
            "Canvas Plot MCP selection read",
        )
        canvas_context_revision = canvas_live.get("revision")
        if not (
            canvas_live.get("available") is True
            and canvas_live.get("project_id") == project_id
            and canvas_live.get("active_panel_id") == "canvas-plot"
            and canvas_live.get("active_scene_id") is None
            and canvas_live.get("selection_section") == "Canvas Plot"
            and canvas_live.get("selection_length") == len(canvas_selection)
            and type(canvas_context_revision) is int
            and canvas_context_revision > resumed_revision
        ):
            raise RuntimeError(
                f"Canvas Plot live context did not match publication: {canvas_live!r}"
            )
        if not (
            canvas_selection_result.get("available") is True
            and canvas_selection_result.get("selection") == canvas_selection
            and canvas_selection_result.get("length") == len(canvas_selection)
            and canvas_selection_result.get("revision") == canvas_context_revision
        ):
            raise RuntimeError(
                "Canvas Plot current selection did not match publication: "
                f"{canvas_selection_result!r}"
            )
        canvas_plot = _structured(
            await session.call_tool("logosforge_get_canvas_plot", {}),
            "Canvas Plot MCP selected-project read",
        )
        canvas_plot_revision = canvas_plot.get("revision")
        if not (
            canvas_plot.get("project_id") == project_id
            and isinstance(canvas_plot_revision, str)
            and len(canvas_plot_revision) == 64
            and all(
                char in "0123456789abcdef" for char in canvas_plot_revision
            )
            and canvas_plot.get("nodes") == []
            and canvas_plot.get("links") == []
            and canvas_plot.get("frames") == []
        ):
            raise RuntimeError(
                "Canvas Plot MCP read did not use the live selected project: "
                f"{canvas_plot!r}"
            )


def smoke(
    *,
    node: str,
    driver_script: Path,
    manager_module: Path,
    core_executable: Path,
    mcp_executable: Path,
) -> None:
    for label, file_path in (
        ("CoreManager driver", driver_script),
        ("compiled CoreManager", manager_module),
        ("frozen core", core_executable),
        ("frozen MCP", mcp_executable),
    ):
        if not file_path.resolve().is_file():
            raise RuntimeError(f"{label} is missing: {file_path.resolve()}")

    with tempfile.TemporaryDirectory(
        prefix="logosforge-live-context-e2e-",
        ignore_cleanup_errors=True,
    ) as temp:
        work = Path(temp).resolve()
        descriptor = work / "mcp-runtime-v1.json"
        driver = _Driver(
            node=node,
            script=driver_script.resolve(),
            manager=manager_module.resolve(),
            core=core_executable.resolve(),
            db=work / "logosforge.db",
            descriptor=descriptor,
            port=_available_port(),
        )
        try:
            ready = driver.wait_ready()
            base_url = ready.get("baseUrl")
            auth_token = ready.get("authToken")
            if not isinstance(base_url, str) or not base_url.startswith(
                "http://127.0.0.1:"
            ):
                raise RuntimeError(f"driver returned an unsafe core URL: {base_url!r}")
            if not isinstance(auth_token, str) or len(auth_token) < 32:
                raise RuntimeError("driver returned an invalid API bearer token")
            if "liveContextToken" in (ready.get("statusKeys") or []):
                raise RuntimeError("CoreStatus exposed the live-context capability")
            descriptor_payload = json.loads(descriptor.read_text(encoding="utf-8"))
            if any(
                "live_context" in str(key).lower() or "capability" in str(key).lower()
                for key in descriptor_payload
            ):
                raise RuntimeError(
                    "runtime descriptor exposed the live-context capability"
                )

            project = _api_json(
                base_url,
                auth_token,
                "POST",
                "/api/projects",
                {"title": "Live context E2E", "narrative_engine": "novel"},
            )
            project_id = int(project["id"])
            scene = _api_json(
                base_url,
                auth_token,
                "POST",
                f"/api/projects/{project_id}/scenes",
                {"title": "Opening", "content": "The bridge is awake."},
            )
            scene_id = int(scene["id"])
            selection = "selected through the real CoreManager"
            driver.command(
                "publish",
                context={
                    "projectId": project_id,
                    "activePanelId": "manuscript",
                    "activeSceneId": scene_id,
                    "selectionSection": "Manuscript",
                    "selection": selection,
                },
            )

            connector_live = _connector(
                base_url, auth_token, project_id, "get_live_context"
            )
            connector_selection = _connector(
                base_url, auth_token, project_id, "get_current_selection"
            )
            connector_scene = _connector(
                base_url, auth_token, project_id, "get_active_scene"
            )
            for label, response in (
                ("live context", connector_live),
                ("selection", connector_selection),
                ("active scene", connector_scene),
            ):
                if response.get("ok") is not True:
                    raise RuntimeError(f"connector {label} read failed: {response!r}")
            _assert_published(
                connector_live.get("result") or {},
                connector_selection.get("result") or {},
                connector_scene.get("result") or {},
                project_id=project_id,
                scene_id=scene_id,
                expected_selection=selection,
            )

            asyncio.run(
                asyncio.wait_for(
                    _exercise_mcp(
                        driver=driver,
                        mcp_executable=mcp_executable.resolve(),
                        descriptor=descriptor,
                        base_url=base_url,
                        auth_token=auth_token,
                        project_id=project_id,
                        scene_id=scene_id,
                        selection=selection,
                    ),
                    timeout=75,
                )
            )
            driver.command("stop")
        except Exception:
            if driver._logs:
                print("\n".join(driver._logs[-50:]))
            raise
        finally:
            driver.close()

    print(
        "Real CoreManager live context reached all connector and MCP reads, "
        "cleared on suspension without resurrection, resumed at a newer revision, "
        "and published Canvas Plot focus for a selected-project board read."
    )


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    desktop_dir = script_dir.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default="node")
    parser.add_argument(
        "--driver",
        type=Path,
        default=script_dir / "live-context-core-manager-driver.cjs",
    )
    parser.add_argument(
        "--manager",
        type=Path,
        default=desktop_dir / "dist-electron" / "core-manager.js",
    )
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--mcp", type=Path, required=True)
    args = parser.parse_args()
    smoke(
        node=args.node,
        driver_script=args.driver,
        manager_module=args.manager,
        core_executable=args.core,
        mcp_executable=args.mcp,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
