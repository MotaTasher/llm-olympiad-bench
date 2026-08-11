#!/usr/bin/env python3
"""Local step-by-step GeoGebra viewer for model solutions.

The viewer renders a *scene*: an ordered list of construction steps, each one a
caption plus GeoGebra commands. The browser page replays the commands up to the
selected step, so a solution can be followed the way it was written.

Usage:

    python scripts/geogebra_view.py run-output/geogebra/task_03.json
    python scripts/geogebra_view.py --serve --port 8770
    python scripts/geogebra_view.py scene.json --export /tmp/task_03.html

While the server runs, the scene can be replaced either by editing the file
(the page picks up the change within a second) or by posting a new one:

    curl -X POST --data-binary @scene.json http://127.0.0.1:8770/api/scene

The scene format is documented in docs/GEOGEBRA_VIEWER.md. This script uses the
standard library only and never touches benchmark logs or scoring sidecars.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

VIEWER_DIR = Path(__file__).resolve().parent / "geogebra_viewer"
INDEX_FILE = VIEWER_DIR / "index.html"
VIEWER_JS = VIEWER_DIR / "viewer.js"
DEFAULT_PORT = 8770
MAX_BODY_BYTES = 4 * 1024 * 1024

EMPTY_SCENE: dict[str, Any] = {
    "title": "Сцена не задана",
    "source": "Отредактируйте файл сцены или отправьте POST /api/scene",
    "steps": [{"title": "Пусто", "commands": []}],
}


# --------------------------------------------------------------------------- #
# scene validation
# --------------------------------------------------------------------------- #

KNOWN_APPS = {"classic", "geometry", "graphing", "3d", "suite"}


def validate_scene(scene: Any) -> list[str]:
    """Return human-readable problems; an empty list means the scene is usable."""
    problems: list[str] = []
    if not isinstance(scene, dict):
        return ["scene must be a JSON object"]

    app = scene.get("app", "classic")
    if not isinstance(app, str) or app not in KNOWN_APPS:
        problems.append(f"app must be one of {sorted(KNOWN_APPS)}, got {app!r}")

    for key in ("title", "source"):
        if key in scene and not isinstance(scene[key], str):
            problems.append(f"{key} must be a string")

    if "view" in scene and not isinstance(scene["view"], dict):
        problems.append("view must be an object")

    if "setup" in scene and not _is_command_list(scene["setup"]):
        problems.append("setup must be a list of strings")

    steps = scene.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps must be a non-empty list")
        return problems

    for index, step in enumerate(steps, start=1):
        where = f"step {index}"
        if not isinstance(step, dict):
            problems.append(f"{where} must be an object")
            continue
        if not _is_command_list(step.get("commands", [])):
            problems.append(f"{where}: commands must be a list of strings")
        for key in ("title", "text"):
            if key in step and not isinstance(step[key], str):
                problems.append(f"{where}: {key} must be a string")
        if "highlight" in step and not _is_command_list(step["highlight"]):
            problems.append(f"{where}: highlight must be a list of object names")
        if "view" in step and not isinstance(step["view"], dict):
            problems.append(f"{where}: view must be an object")

    return problems


def _is_command_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


# --------------------------------------------------------------------------- #
# scene state
# --------------------------------------------------------------------------- #


class SceneState:
    """Current scene, reloaded from disk whenever the file changes."""

    def __init__(self, path: Path | None) -> None:
        self._lock = threading.Lock()
        self._path = path
        self._mtime: float | None = None
        self._scene: dict[str, Any] = EMPTY_SCENE
        self._error: str | None = None
        self._version = 0
        if path is not None:
            self._reload_locked()

    @property
    def path(self) -> Path | None:
        return self._path

    def snapshot(self) -> dict[str, Any]:
        """Reload the file if it changed, then return the payload for the page."""
        with self._lock:
            if self._path is not None:
                try:
                    mtime = self._path.stat().st_mtime
                except OSError as exc:
                    self._set_error(f"файл сцены недоступен: {exc}")
                    mtime = None
                if mtime is not None and mtime != self._mtime:
                    self._reload_locked()
            payload: dict[str, Any] = {"version": self._version, "scene": self._scene}
            if self._error:
                payload["error"] = self._error
            if self._path is not None:
                payload["path"] = str(self._path)
            return payload

    def replace(self, scene: dict[str, Any]) -> int:
        """Install a scene received over HTTP; returns the new version."""
        with self._lock:
            self._scene = scene
            self._error = None
            self._version += 1
            # A posted scene holds until the watched file is edited again, so
            # adopt the file's current mtime instead of forcing a reload.
            if self._path is not None:
                try:
                    self._mtime = self._path.stat().st_mtime
                except OSError:
                    self._mtime = None
            return self._version

    def _reload_locked(self) -> None:
        assert self._path is not None
        try:
            raw = self._path.read_text(encoding="utf-8")
            self._mtime = self._path.stat().st_mtime
        except OSError as exc:
            self._set_error(f"файл сцены недоступен: {exc}")
            return
        try:
            scene = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._set_error(f"сцена не парсится: строка {exc.lineno}, {exc.msg}")
            return
        problems = validate_scene(scene)
        if problems:
            self._set_error("сцена невалидна: " + "; ".join(problems[:3]))
            return
        self._scene = scene
        self._error = None
        self._version += 1

    def _set_error(self, message: str) -> None:
        if self._error != message:
            self._error = message
            self._version += 1


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "GeoGebraViewer/1.0"
    state: SceneState  # injected on the server instance

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send_bytes(200, "text/html; charset=utf-8", INDEX_FILE.read_bytes())
        elif path == "/viewer.js":
            self._send_bytes(200, "application/javascript; charset=utf-8", VIEWER_JS.read_bytes())
        elif path == "/api/scene":
            self._send_json(200, self.state.snapshot())
        elif path == "/health":
            self._send_json(200, {"ok": True})
        elif path == "/favicon.ico":
            self._send_bytes(204, "image/x-icon", b"")
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.split("?", 1)[0] != "/api/scene":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "bad Content-Length"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(400, {"error": f"body must be 1..{MAX_BODY_BYTES} bytes"})
            return
        body = self.rfile.read(length)
        try:
            scene = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": f"invalid JSON: {exc}"})
            return
        problems = validate_scene(scene)
        if problems:
            self._send_json(400, {"error": "invalid scene", "problems": problems})
            return
        version = self.state.replace(scene)
        self._send_json(200, {"ok": True, "version": version})

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        """Keep the console readable; only errors are worth printing."""
        status = args[1] if len(args) > 1 else ""
        if isinstance(status, str) and status.startswith(("4", "5")):
            sys.stderr.write("geogebra-view: %s\n" % (fmt % args))


def bind_server(host: str, port: int, state: SceneState) -> ThreadingHTTPServer:
    """Bind the first free port starting at `port`."""
    last_error: OSError | None = None
    for candidate in range(port, port + 10):
        try:
            server = ThreadingHTTPServer((host, candidate), ViewerHandler)
        except OSError as exc:
            last_error = exc
            continue
        ViewerHandler.state = state
        return server
    raise SystemExit(f"no free port in {port}..{port + 9}: {last_error}")


# --------------------------------------------------------------------------- #
# static export
# --------------------------------------------------------------------------- #


def export_html(scene: dict[str, Any], destination: Path) -> None:
    """Write a self-contained page with the scene and the engine inlined."""
    template = INDEX_FILE.read_text(encoding="utf-8")
    payload = json.dumps(scene, ensure_ascii=False)
    # </script> inside string data would close the tag early.
    payload = payload.replace("</", "<\\/")
    injected = f"<script>window.__SCENE__ = {payload};</script>\n</head>"
    if "</head>" not in template:
        raise SystemExit("viewer template has no </head>; cannot export")
    page = template.replace("</head>", injected, 1)

    engine_tag = '<script src="viewer.js"></script>'
    if engine_tag not in page:
        raise SystemExit("viewer template does not load viewer.js; cannot export")
    engine = VIEWER_JS.read_text(encoding="utf-8")
    page = page.replace(engine_tag, "<script>\n" + engine + "\n</script>", 1)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding="utf-8")


def load_scene_file(path: Path) -> dict[str, Any]:
    try:
        scene = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    problems = validate_scene(scene)
    if problems:
        raise SystemExit(f"{path}: invalid scene\n  - " + "\n  - ".join(problems))
    return scene


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local step-by-step GeoGebra viewer.")
    parser.add_argument("scene", nargs="?", type=Path, help="scene JSON file to watch")
    parser.add_argument("--serve", action="store_true", help="start without a scene file")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"first port to try (default {DEFAULT_PORT})")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    parser.add_argument("--export", type=Path, metavar="HTML", help="write a standalone page and exit")
    parser.add_argument("--check", action="store_true", help="validate the scene file and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not INDEX_FILE.exists():
        raise SystemExit(f"viewer template missing: {INDEX_FILE}")

    if args.check or args.export:
        if args.scene is None:
            raise SystemExit("--check and --export require a scene file")
        scene = load_scene_file(args.scene)
        if args.check:
            print(f"{args.scene}: ok, {len(scene['steps'])} step(s)")
        if args.export:
            export_html(scene, args.export)
            print(f"wrote {args.export}")
        return 0

    if args.scene is None and not args.serve:
        raise SystemExit("pass a scene file or --serve")
    if args.scene is not None and not args.scene.exists():
        raise SystemExit(f"scene file not found: {args.scene}")

    state = SceneState(args.scene.resolve() if args.scene else None)
    server = bind_server(args.host, args.port, state)
    url = f"http://{args.host}:{server.server_address[1]}/"
    watching = f"следим за {state.path}" if state.path else "ждём POST /api/scene"
    print(f"GeoGebra viewer: {url}  ({watching})")
    print("Ctrl+C — остановить")
    if not args.no_open:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
