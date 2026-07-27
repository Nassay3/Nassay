"""Run the Nassay development app with one Python command.

The application itself uses Node.js.  This launcher downloads a private,
portable Node.js runtime and pnpm inside the project when they are missing,
then starts both the API and the web interface.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from hashlib import sha256
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_DIR / ".runtime"
NODE_VERSION = "24.11.1"
PNPM_PREFIX = RUNTIME_DIR / "pnpm"
PNPM_CLI = PNPM_PREFIX / "node_modules" / "pnpm" / "bin" / "pnpm.cjs"
LOCKFILE = PROJECT_DIR / "pnpm-lock.yaml"
INSTALL_STAMP = RUNTIME_DIR / "pnpm-lock.sha256"
API_DIR = PROJECT_DIR / "artifacts" / "api-server"
WEB_DIR = PROJECT_DIR / "artifacts" / "trading-terminal"
VITE_CLI = WEB_DIR / "node_modules" / "vite" / "bin" / "vite.js"


def node_distribution() -> tuple[Path, str, str, Path, Path]:
    """Return the private Node layout for Windows, macOS, or Linux."""
    machine = platform.machine().lower()
    arm64 = machine in {"arm64", "aarch64"}

    if sys.platform == "win32":
        arch = "arm64" if arm64 else "x64"
        platform_name = f"win-{arch}"
        archive_kind = "zip"
        node_relative = Path("node.exe")
        npm_relative = Path("npm.cmd")
    elif sys.platform == "darwin":
        arch = "arm64" if arm64 else "x64"
        platform_name = f"darwin-{arch}"
        archive_kind = "tar.gz"
        node_relative = Path("bin") / "node"
        npm_relative = Path("bin") / "npm"
    elif sys.platform.startswith("linux"):
        arch = "arm64" if arm64 else "x64"
        platform_name = f"linux-{arch}"
        archive_kind = "tar.xz"
        node_relative = Path("bin") / "node"
        npm_relative = Path("bin") / "npm"
    else:
        raise RuntimeError(f"Unsupported operating system: {sys.platform}")

    folder_name = f"node-v{NODE_VERSION}-{platform_name}"
    folder = RUNTIME_DIR / folder_name
    url = f"https://nodejs.org/dist/v{NODE_VERSION}/{folder_name}.{archive_kind}"
    return folder, url, archive_kind, node_relative, npm_relative


NODE_FOLDER, NODE_URL, NODE_ARCHIVE_KIND, NODE_RELATIVE, NPM_RELATIVE = (
    node_distribution()
)


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
    path_npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if path_node and path_npm:
        return Path(path_node), Path(path_npm)

    private_node = NODE_FOLDER / NODE_RELATIVE
    private_npm = NODE_FOLDER / NPM_RELATIVE
    if private_node.exists() and private_npm.exists():
        return private_node, private_npm

    local_app_data = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local_app_data:
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

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    archive = RUNTIME_DIR / f"node.{NODE_ARCHIVE_KIND}"

    try:
        download(NODE_URL, archive)
        print("Extracting the private Node.js runtime...", flush=True)
        if NODE_ARCHIVE_KIND == "zip":
            with zipfile.ZipFile(archive) as node_zip:
                node_zip.extractall(RUNTIME_DIR)
        else:
            with tarfile.open(archive, "r:*") as node_tar:
                node_tar.extractall(RUNTIME_DIR)
    except Exception:
        if NODE_FOLDER.exists():
            shutil.rmtree(NODE_FOLDER)
        raise
    finally:
        archive.unlink(missing_ok=True)

    return NODE_FOLDER / NODE_RELATIVE, NODE_FOLDER / NPM_RELATIVE


def git_output(git_exe: str, *arguments: str) -> str:
    result = subprocess.run(
        [git_exe, *arguments],
        cwd=PROJECT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sync_repository() -> None:
    """Fast-forward main when it is safe; never overwrite local work."""
    git_exe = shutil.which("git")
    if not git_exe or not (PROJECT_DIR / ".git").exists():
        print("Git sync skipped: this folder is not a Git checkout.")
        return

    if git_output(git_exe, "status", "--porcelain"):
        print("Git sync skipped: commit or stash local changes first.")
        return

    branch = git_output(git_exe, "branch", "--show-current")
    if branch != "main":
        print(f"Git sync skipped: current branch is {branch or 'detached HEAD'}, not main.")
        return

    print("Checking GitHub for the latest main branch...", flush=True)
    try:
        git_output(git_exe, "fetch", "--prune", "origin", "main")
        counts = git_output(
            git_exe,
            "rev-list",
            "--left-right",
            "--count",
            "HEAD...origin/main",
        ).split()
        ahead, behind = (int(counts[0]), int(counts[1]))
        if ahead == 0 and behind > 0:
            subprocess.run(
                [git_exe, "pull", "--ff-only", "origin", "main"],
                cwd=PROJECT_DIR,
                check=True,
            )
            print("Project updated from GitHub.", flush=True)
        elif ahead or behind:
            print(
                f"Automatic sync paused: local is {ahead} ahead and {behind} behind. "
                "Resolve or publish these commits before switching devices."
            )
        else:
            print("Project is already up to date.", flush=True)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Git sync warning: {error}. Starting the local copy.", file=sys.stderr)


def lockfile_digest() -> str:
    return sha256(LOCKFILE.read_bytes()).hexdigest()


def packages_are_current() -> bool:
    if not VITE_CLI.exists() or not (API_DIR / "node_modules" / "esbuild").exists():
        return False
    try:
        return INSTALL_STAMP.read_text(encoding="utf-8").strip() == lockfile_digest()
    except (FileNotFoundError, OSError):
        return False


def mark_packages_current() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    INSTALL_STAMP.write_text(lockfile_digest(), encoding="utf-8")


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
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


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
        if "--no-sync" not in sys.argv[1:]:
            sync_repository()
        node_exe, npm_cmd = install_node()
        node_folder = node_exe.parent
        environment = os.environ.copy()
        environment["PATH"] = (
            f"{node_folder}{os.pathsep}{environment.get('PATH', '')}"
        )
        # Windows may trust a corporate/system root that Node's bundled CA
        # store does not include. Using the system store keeps Binance HTTPS
        # history and the live WebSocket available without disabling TLS checks.
        if os.name == "nt":
            node_options = environment.get("NODE_OPTIONS", "")
            if "--use-system-ca" not in node_options:
                environment["NODE_OPTIONS"] = f"--use-system-ca {node_options}".strip()
        if app_is_running():
            print("Nassay is already running at http://localhost:5173")
            return 0

        packages_are_ready = packages_are_current()
        if not packages_are_ready:
            install_pnpm(environment, npm_cmd)
            print("Installing or updating project packages...", flush=True)
            subprocess.run(
                [str(node_exe), str(PNPM_CLI), "install"],
                cwd=PROJECT_DIR,
                env=environment,
                check=True,
            )
            mark_packages_current()

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
            "Check your internet connection, then run: python run.py "
            "(or python3 run.py on macOS).",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
