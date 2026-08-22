"""OllamaInstaller - detect, install, and start Ollama on the local device.

Cross-platform (Windows / macOS / Linux) helper used by the startup screen
so a user with a completely clean machine never has to leave the app to get
running. Pure Python + stdlib (+ ``requests``, already a hard dependency) -
no Qt here; the GUI wraps :func:`ensure_ollama` in a worker thread and turns
its ``InstallProgress`` callbacks into Qt signals.

Design:
  - ``detect()`` distinguishes three states: RUNNING (the service answers on
    the configured base URL), INSTALLED_NOT_RUNNING (the ``ollama`` binary
    is on PATH / in a known install location but the server isn't up yet),
    and NOT_INSTALLED.
  - ``install()`` uses the officially supported install path for each OS:
      * Linux  -> the official install script (``curl -fsSL https://ollama.com/install.sh | sh``),
        the same one-liner ollama.com documents; always installs the latest
        stable release.
      * macOS  -> Homebrew (``brew install ollama``) if Homebrew is present,
        otherwise falls back to downloading the official .zip app bundle
        from ollama.com and unpacking it into /Applications - no
        Xcode/build toolchain required either way.
      * Windows -> ``winget install --id Ollama.Ollama`` if winget is
        available (default on Windows 10 21H2+/11), otherwise downloads the
        official ``OllamaSetup.exe`` and runs it silently.
  - ``start()`` launches the local server (``ollama serve``, or the platform
    app bundle) as a detached background process and polls ``/api/tags``
    until it answers or a timeout elapses.
  - Every step raises :class:`InstallerError` with a human-readable message
    on failure instead of letting a raw ``subprocess``/network exception
    escape - the GUI shows that message verbatim in a blocking error dialog.
"""
from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from prism_core import config, ollama

INSTALL_SCRIPT_URL = "https://ollama.com/install.sh"
WINDOWS_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
MACOS_APP_ZIP_URL = "https://ollama.com/download/Ollama-darwin.zip"

START_POLL_TIMEOUT_S = 45
START_POLL_INTERVAL_S = 1.0
INSTALL_SUBPROCESS_TIMEOUT_S = 900  # 15 min - large installer/first-run download


class InstallerError(RuntimeError):
    """Any failure detecting, installing, or starting Ollama on this device.

    ``.detail`` carries the raw underlying error (subprocess stderr, HTTP
    exception, etc.) for logs; the exception's string form is always a
    plain-language sentence safe to show directly in a dialog.
    """

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


@dataclass(frozen=True)
class InstallProgress:
    stage: str     # "detecting" | "downloading" | "installing" | "starting" | "done"
    message: str
    # 0-100 when a concrete download/step percentage is known; None when the
    # stage's duration can't be estimated (e.g. running the install script)
    # so the GUI should show an indeterminate/busy progress bar instead.
    percent: Optional[float] = None


ProgressCB = Optional[Callable[[InstallProgress], None]]

# Called (with no arguments, from whatever thread the installer is running
# on) only if the Linux install actually needs an administrator password -
# i.e. the user isn't root and passwordless sudo isn't already configured.
# Should return the password string, or None/"" if the user cancelled.
SudoPasswordProvider = Optional[Callable[[], Optional[str]]]


def _emit(cb: ProgressCB, stage: str, message: str, percent: Optional[float] = None) -> None:
    if cb is not None:
        cb(InstallProgress(stage, message, percent))


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def is_running(*, timeout: float = 3.0) -> bool:
    return ollama.is_available(timeout=timeout)


def find_binary() -> Optional[str]:
    """Locate the ``ollama`` executable, checking PATH first, then the
    common per-OS install locations a fresh install/session might not
    have on PATH yet (e.g. right after a Homebrew or winget install,
    before the shell has re-sourced its environment)."""
    on_path = shutil.which("ollama")
    if on_path:
        return on_path

    system = platform.system()
    candidates: list[Path] = []
    if system == "Darwin":
        candidates += [
            Path("/usr/local/bin/ollama"),
            Path("/opt/homebrew/bin/ollama"),
            Path("/Applications/Ollama.app/Contents/Resources/ollama"),
        ]
    elif system == "Linux":
        candidates += [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama")]
    elif system == "Windows":
        local = Path.home() / "AppData" / "Local" / "Programs" / "Ollama"
        candidates += [local / "ollama.exe"]

    for path in candidates:
        if path.exists():
            return str(path)
    return None


def is_installed() -> bool:
    return find_binary() is not None


@dataclass(frozen=True)
class DetectResult:
    running: bool
    installed: bool
    binary_path: Optional[str]

    @property
    def needs_install(self) -> bool:
        return not self.installed

    @property
    def needs_start(self) -> bool:
        return self.installed and not self.running


def detect() -> DetectResult:
    running = is_running()
    if running:
        return DetectResult(True, True, find_binary())
    binary = find_binary()
    return DetectResult(False, binary is not None, binary)


# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------

def _run(cmd: list[str], *, timeout: float, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, cwd=cwd, timeout=timeout,
            capture_output=True, text=True,
        )
    except FileNotFoundError as exc:
        raise InstallerError(f"Couldn't run {cmd[0]!r} - it isn't on this device.", str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise InstallerError(
            f"{cmd[0]} took too long to finish (over {int(timeout // 60)} minutes).",
            str(exc),
        ) from exc


def _download(url: str, dest: Path, cb: ProgressCB, *, label: str = "Ollama") -> None:
    _emit(cb, "downloading", f"Downloading {url.rsplit('/', 1)[-1]}\u2026", percent=0)
    try:
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            done = 0
            with dest.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done / total * 100
                        _emit(cb, "downloading", f"Downloading {label}\u2026 {int(pct)}%", percent=pct)
                    else:
                        mb_done = done / (1024 * 1024)
                        _emit(cb, "downloading", f"Downloading {label}\u2026 {mb_done:,.0f} MB", percent=None)
    except requests.RequestException as exc:
        raise InstallerError(
            "Couldn't download the Ollama installer. Check your internet "
            "connection and try again.",
            str(exc),
        ) from exc


# --------------------------------------------------------------------------
# Linux sudo handling
# --------------------------------------------------------------------------

def linux_sudo_password_required() -> bool:
    """True if the official install script will need to prompt for a sudo
    password on this machine - i.e. we're not already root and passwordless
    sudo (``NOPASSWD`` or a still-live credential cache) isn't available."""
    if platform.system() != "Linux":
        return False
    try:
        if os.geteuid() == 0:  # already root
            return False
    except AttributeError:
        pass
    if shutil.which("sudo") is None:
        # No sudo at all - the install script's own `$SUDO` calls will
        # simply be skipped/no-ops in that case, nothing for us to supply.
        return False
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"], capture_output=True, timeout=5,
        )
        return result.returncode != 0
    except Exception:
        return True


def _fetch_install_script() -> str:
    """Download the official install script, tolerating transient network
    blips instead of failing on the first hiccup. Tries ``requests`` a few
    times with backoff, then falls back to the system ``curl`` (which on
    Linux often picks up proxy/CA config - env proxies, corporate root
    certs installed system-wide, etc. - that Python's ``requests`` may not
    see), before giving up entirely.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            resp = requests.get(INSTALL_SCRIPT_URL, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))

    curl = shutil.which("curl")
    if curl:
        try:
            result = subprocess.run(
                [curl, "-fsSL", INSTALL_SCRIPT_URL],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except Exception:
            pass

    raise InstallerError(
        "Couldn't reach ollama.com to download the installer. Check your "
        "internet connection (and any firewall/proxy) and try again.",
        str(last_exc) if last_exc else "curl fallback also failed",
    )


def _install_linux(cb: ProgressCB, sudo_password_provider: SudoPasswordProvider = None) -> None:
    """Official install script - always fetches the current stable build,
    same command ollama.com documents for every distro/architecture.

    The script shells out to ``sudo`` internally (to write to /usr/bin,
    install the systemd service, etc). Since it runs headless as a
    subprocess with no attached terminal, plain ``sudo`` can't prompt for a
    password there - so when a password is actually needed we ask the GUI
    for one up front (via ``sudo_password_provider``) and feed it to sudo
    through a throwaway ``SUDO_ASKPASS`` helper instead of ever touching a
    terminal.
    """
    _emit(cb, "installing", "Preparing the Ollama installer\u2026")
    script = _fetch_install_script()

    needs_password = linux_sudo_password_required()
    env = None
    askpass_dir: Optional[str] = None
    try:
        if needs_password:
            if sudo_password_provider is None:
                raise InstallerError(
                    "Installing Ollama needs administrator (sudo) access on "
                    "Linux, but no password prompt is available here. "
                    "Please install it manually from https://ollama.com/download."
                )
            password = sudo_password_provider()
            if not password:
                raise InstallerError(
                    "Installation cancelled - Ollama needs administrator "
                    "access to install on Linux."
                )

            # A tiny SUDO_ASKPASS helper that just hands sudo the password,
            # plus a `sudo` shim ahead of the real one on PATH so the
            # install script's own bare `sudo ...` calls automatically pick
            # up `-A` (ask via helper) instead of trying to read a tty.
            askpass_dir = tempfile.mkdtemp(prefix="prism_ollama_install_")
            askpass_path = Path(askpass_dir) / "askpass.sh"
            askpass_path.write_text(f"#!/bin/sh\necho {shlex.quote(password)}\n")
            askpass_path.chmod(0o700)
            password = None  # don't keep the plaintext around longer than needed

            real_sudo = shutil.which("sudo") or "/usr/bin/sudo"
            sudo_shim_path = Path(askpass_dir) / "sudo"
            sudo_shim_path.write_text(f"#!/bin/sh\nexec {shlex.quote(real_sudo)} -A \"$@\"\n")
            sudo_shim_path.chmod(0o700)

            env = os.environ.copy()
            env["SUDO_ASKPASS"] = str(askpass_path)
            env["PATH"] = f"{askpass_dir}:{env.get('PATH', '')}"
            _emit(cb, "installing", "Installing Ollama with the password you provided\u2026")
        else:
            _emit(cb, "installing", "Installing Ollama\u2026")

        result = subprocess.run(
            ["sh", "-c", script],
            capture_output=True, text=True, timeout=INSTALL_SUBPROCESS_TIMEOUT_S,
            env=env,
        )
    finally:
        if askpass_dir:
            shutil.rmtree(askpass_dir, ignore_errors=True)

    if result.returncode != 0:
        stderr_tail = result.stderr[-2000:]
        lowered = stderr_tail.lower()
        if needs_password and (
            "incorrect password" in lowered
            or "sorry, try again" in lowered
            or "no password was provided" in lowered
            or "authentication failure" in lowered
        ):
            raise InstallerError(
                "That administrator password wasn't accepted. Please try again.",
                stderr_tail,
            )
        if "command not found" in lowered and ("curl" in lowered or "tar" in lowered or "gzip" in lowered):
            raise InstallerError(
                "This device is missing a tool the Ollama installer needs "
                "(curl, tar, or gzip). Install it with your package manager "
                "(e.g. `sudo apt install curl tar gzip` on Ubuntu/Debian) "
                "and try again.",
                stderr_tail,
            )
        if "unsupported" in lowered and ("arch" in lowered or "distro" in lowered or "os" in lowered):
            raise InstallerError(
                "This Linux distribution or architecture isn't supported by "
                "the official Ollama installer. Check "
                "https://ollama.com/download for supported options.",
                stderr_tail,
            )
        if "permission denied" in lowered:
            raise InstallerError(
                "The installer hit a permissions error writing system "
                "files. Make sure this user has sudo access, then try again.",
                stderr_tail,
            )
        raise InstallerError(
            "The Ollama install script failed. You may need to install it "
            "manually from https://ollama.com/download.",
            stderr_tail,
        )


def _install_macos(cb: ProgressCB, sudo_password_provider: SudoPasswordProvider = None) -> None:
    brew = shutil.which("brew")
    if brew:
        _emit(cb, "installing", "Installing Ollama via Homebrew\u2026")
        result = _run([brew, "install", "ollama"], timeout=INSTALL_SUBPROCESS_TIMEOUT_S)
        if result.returncode != 0:
            raise InstallerError(
                "`brew install ollama` failed. You can install it manually "
                "from https://ollama.com/download.",
                result.stderr[-2000:],
            )
        return

    # No Homebrew: download the official app bundle and unpack it directly,
    # matching what a user dragging Ollama.app into /Applications would do.
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "Ollama-darwin.zip"
        _download(MACOS_APP_ZIP_URL, zip_path, cb)
        _emit(cb, "installing", "Installing Ollama.app to /Applications\u2026")
        result = _run(
            ["ditto", "-x", "-k", str(zip_path), "/Applications"],
            timeout=180,
        )
        if result.returncode != 0:
            raise InstallerError(
                "Couldn't unpack Ollama.app into /Applications. Try "
                "installing it manually from https://ollama.com/download.",
                result.stderr[-2000:],
            )


def _install_windows(cb: ProgressCB, sudo_password_provider: SudoPasswordProvider = None) -> None:
    winget = shutil.which("winget")
    if winget:
        _emit(cb, "installing", "Installing Ollama via winget\u2026")
        result = _run(
            [winget, "install", "--id", "Ollama.Ollama", "-e",
             "--accept-source-agreements", "--accept-package-agreements",
             "--silent"],
            timeout=INSTALL_SUBPROCESS_TIMEOUT_S,
        )
        if result.returncode == 0:
            return
        # Fall through to the direct installer if winget itself failed
        # (e.g. no matching source configured) rather than giving up.

    with tempfile.TemporaryDirectory() as tmp:
        exe_path = Path(tmp) / "OllamaSetup.exe"
        _download(WINDOWS_INSTALLER_URL, exe_path, cb)
        _emit(cb, "installing", "Running the Ollama installer silently\u2026")
        result = _run([str(exe_path), "/VERYSILENT", "/NORESTART"], timeout=INSTALL_SUBPROCESS_TIMEOUT_S)
        if result.returncode != 0:
            raise InstallerError(
                "The Ollama installer failed to complete. Try running it "
                "manually from https://ollama.com/download.",
                result.stderr[-2000:],
            )


_INSTALLERS = {"Linux": _install_linux, "Darwin": _install_macos, "Windows": _install_windows}


def install(cb: ProgressCB = None, sudo_password_provider: SudoPasswordProvider = None) -> None:
    """Install the latest stable Ollama release for the current OS.

    Raises :class:`InstallerError` with a plain-language message on any
    failure (unsupported OS, network failure, installer exit code != 0, or
    an incorrect/cancelled sudo password on Linux).
    """
    system = platform.system()
    installer = _INSTALLERS.get(system)
    if installer is None:
        raise InstallerError(
            f"PRISM doesn't know how to auto-install Ollama on {system!r}. "
            "Please install it manually from https://ollama.com/download, "
            "then click Refresh Status."
        )
    installer(cb, sudo_password_provider)
    if find_binary() is None:
        raise InstallerError(
            "The installer finished, but Ollama still couldn't be found on "
            "this device. Please install it manually from "
            "https://ollama.com/download."
        )


# --------------------------------------------------------------------------
# Start
# --------------------------------------------------------------------------

def start(cb: ProgressCB = None) -> None:
    """Launch the local Ollama server in the background and wait for it to
    answer, raising :class:`InstallerError` if it never comes up."""
    _emit(cb, "starting", "Starting Ollama\u2026")
    system = platform.system()

    if system == "Darwin" and Path("/Applications/Ollama.app").exists():
        # The macOS app bundle runs its own menu-bar server; launching it
        # is the supported way to start the service (vs. invoking the CLI
        # server subprocess directly, which the app bundle install doesn't
        # expose the same way the Linux/Windows CLI installs do).
        _run(["open", "-a", "Ollama"], timeout=15)
    else:
        binary = find_binary()
        if binary is None:
            raise InstallerError("Ollama isn't installed on this device yet.")
        creationflags = 0
        kwargs: dict = {}
        if system == "Windows":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            kwargs["creationflags"] = creationflags
        try:
            subprocess.Popen(
                [binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=(system != "Windows"),
                **kwargs,
            )
        except OSError as exc:
            raise InstallerError(f"Couldn't start Ollama: {exc}", str(exc)) from exc

    deadline = time.monotonic() + START_POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        if is_running(timeout=2.0):
            _emit(cb, "done", "Ollama is running.")
            return
        time.sleep(START_POLL_INTERVAL_S)
    raise InstallerError(
        "Ollama was installed but didn't start responding within "
        f"{START_POLL_TIMEOUT_S} seconds. Try launching it manually, then "
        "click Refresh Status."
    )


# --------------------------------------------------------------------------
# One-shot orchestration used by the GUI's "Install Ollama" button
# --------------------------------------------------------------------------

def ensure_ollama(cb: ProgressCB = None, sudo_password_provider: SudoPasswordProvider = None) -> None:
    """Detect -> install (if needed) -> start (if needed). Raises
    :class:`InstallerError` on any unrecoverable failure; returns normally
    only once ``/api/tags`` is confirmed reachable.

    ``sudo_password_provider``, if given, is called (with no arguments)
    only if a Linux install actually needs an administrator password - it
    should return the password to use, or None/"" to cancel.
    """
    _emit(cb, "detecting", "Checking for Ollama\u2026")
    state = detect()
    if state.running:
        _emit(cb, "done", "Ollama is already running.")
        return
    if not state.installed:
        install(cb, sudo_password_provider)
    start(cb)


def supported_platforms() -> tuple[str, ...]:
    return tuple(_INSTALLERS.keys())


def is_platform_supported() -> bool:
    return platform.system() in _INSTALLERS