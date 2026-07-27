"""Run the Nassay development app with one Python command.

The application itself uses Node.js.  This launcher downloads a private,
portable Node.js runtime and pnpm inside the project when they are missing,
then starts both the API and the web interface.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_DIR / ".runtime"
NODE_VERSION = "24.11.1"
NODE_FOLDER = RUNTIME_DIR / f"node-v{NODE_VERSION}-win-x64"
PNPM_PREFIX = RUNTIME_DIR / "pnpm"
PNPM_CLI = PNPM_PREFIX / "node_modules" / "pnpm" / "bin" / "pnpm.cjs"
API_DIR = PROJECT_DIR / "artifacts" / "api-server"
WEB_DIR = PROJECT_DIR / "artifacts" / "trading-terminal"
VITE_CLI = WEB_DIR / "node_modules" / "vite" / "bin" / "vite.js"


def download(url: str, destination: Path) -> None:
    print(f"Downloading {url}", flush=True)

    def report(blocks: int, block_size: int, total: int) -> None:
        if total > 0:
            percent = min(100, blocks * block_size * 100 // total)
            print(f"\rProgress: {percent:3d}%", end="", flush=True)

    urllib.request.urlretrieve(url, destination, report)
    print()


def app_is_running() -> bool:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:5000/api/healthz", timeout=1
        ) as api_response:
            api_ok = api_response.status == 200
        with urllib.request.urlopen(
            "http://127.0.0.1:5173", timeout=1
        ) as web_response:
            web_ok = web_response.status == 200
        return api_ok and web_ok
    except Exception:
        return False


def find_existing_node() -> tuple[Path, Path] | None:
    """Find Node from PATH, this project's cache, or the Codex desktop app."""
    path_node = shutil.which("node")
    path_npm = shutil.which("npm.cmd")
    if path_node and path_npm:
        return Path(path_node), Path(path_npm)

    private_node = NODE_FOLDER / "node.exe"
    private_npm = NODE_FOLDER / "npm.cmd"
    if private_node.exists() and private_npm.exists():
        return private_node, private_npm

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        runtime_pattern = (
            Path(local_app_data) / "OpenAI" / "Codex" / "runtimes" / "cua_node"
        )
        candidates = sorted(
            runtime_pattern.glob("*/bin/node.exe"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for node_exe in candidates:
            npm_cmd = node_exe.with_name("npm.cmd")
            if npm_cmd.exists():
                return node_exe, npm_cmd

    return None


def install_node() -> tuple[Path, Path]:
    existing = find_existing_node()
    if existing:
        return existing

    if os.name != "nt" or sys.maxsize <= 2**32:
        raise RuntimeError("This launcher currently supports 64-bit Windows only.")

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    url = (
        f"https://nodejs.org/dist/v{NODE_VERSION}/"
        f"node-v{NODE_VERSION}-win-x64.zip"
    )
    archive = RUNTIME_DIR / "node.zip"
    partial_folder = RUNTIME_DIR / f"node-v{NODE_VERSION}-win-x64"

    try:
        download(url, archive)
        print("Extracting the private Node.js runtime...", flush=True)
        with zipfile.ZipFile(archive) as node_zip:
            node_zip.extractall(RUNTIME_DIR)
    except Exception:
        if partial_folder.exists():
            shutil.rmtree(partial_folder)
        raise
    finally:
        archive.unlink(missing_ok=True)

    return NODE_FOLDER / "node.exe", NODE_FOLDER / "npm.cmd"


def install_pnpm(environment: dict[str, str], npm_cmd: Path) -> None:
    if PNPM_CLI.exists():
        return

    print("Installing pnpm inside the project...", flush=True)
    PNPM_PREFIX.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(npm_cmd),
            "install",
            "--prefix",
            str(PNPM_PREFIX),
            "--no-audit",
            "--no-fund",
            "pnpm@10",
        ],
        cwd=PROJECT_DIR,
        env=environment,
        check=True,
    )


def stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()


def run_from_existing_packages(
    node_exe: Path, environment: dict[str, str]
) -> int:
    """Start the two services directly when node_modules is already present."""
    api_environment = environment.copy()
    api_environment["PORT"] = "5000"
    web_environment = environment.copy()
    web_environment.update(
        {
            "PORT": "5173",
            "BASE_PATH": "/",
            "API_ORIGIN": "http://127.0.0.1:5000",
        }
    )

    print("Preparing the API server...", flush=True)
    subprocess.run(
        [str(node_exe), "build.mjs"],
        cwd=API_DIR,
        env=api_environment,
        check=True,
    )

    api = subprocess.Popen(
        [str(node_exe), "--enable-source-maps", "dist/index.mjs"],
        cwd=API_DIR,
        env=api_environment,
    )
    web = subprocess.Popen(
        [
            str(node_exe),
            str(VITE_CLI),
            "--config",
            "vite.config.ts",
            "--host",
            "0.0.0.0",
        ],
        cwd=WEB_DIR,
        env=web_environment,
    )
    children = [api, web]

    try:
        while True:
            for child in children:
                result = child.poll()
                if result is not None:
                    return result
            time.sleep(0.5)
    finally:
        for child in children:
            stop_process_tree(child)


def main() -> int:
    try:
        node_exe, npm_cmd = install_node()
        node_folder = node_exe.parent
        environment = os.environ.copy()
        environment["PATH"] = (
            f"{node_folder}{os.pathsep}{environment.get('PATH', '')}"
        )
        # Windows may trust a corporate/system root that Node's bundled CA
        # store does not include. Using the system store keeps Binance HTTPS
        # history and the live WebSocket available without disabling TLS checks.
        node_options = environment.get("NODE_OPTIONS", "")
        if "--use-system-ca" not in node_options:
            environment["NODE_OPTIONS"] = f"--use-system-ca {node_options}".strip()
        if app_is_running():
            print("Nassay is already running at http://localhost:5173")
            return 0

        packages_are_ready = VITE_CLI.exists() and (
            API_DIR / "node_modules" / "esbuild"
        ).exists()
        if not packages_are_ready:
            install_pnpm(environment, npm_cmd)
            print("Installing project packages (first run only)...", flush=True)
            subprocess.run(
                [str(node_exe), str(PNPM_CLI), "install"],
                cwd=PROJECT_DIR,
                env=environment,
                check=True,
            )

        print("\nStarting Nassay at http://localhost:5173", flush=True)
        print("Press Ctrl+C to stop it.\n", flush=True)
        if packages_are_ready:
            return run_from_existing_packages(node_exe, environment)

        return subprocess.call(
            [str(node_exe), str(PNPM_CLI), "dev"],
            cwd=PROJECT_DIR,
            env=environment,
        )
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"\nCould not start Nassay: {error}", file=sys.stderr)
        print(
            "Check your internet connection, then run: python run.py",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
