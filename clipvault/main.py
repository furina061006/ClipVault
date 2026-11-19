#!/usr/bin/env python3
"""
ClipVault - Windows-style Clipboard Manager for Ubuntu
Keyboard shortcut: Super+V (Win+V equivalent)
"""

import sys
import os
import argparse
import signal
import atexit

# Allow running from the project root: python clipvault/main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipvault import __version__
from clipvault import diagnostics

# Must be enabled before Qt is imported so that a crash inside Qt/C++
# libraries also gets a Python stack dump.
diagnostics.setup()
log = diagnostics.get_logger()

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from clipvault.core.history_manager import HistoryManager
from clipvault.ui.main_window import ClipVaultWindow
from clipvault.ui.tray_icon import TrayIcon
from clipvault.shared.constants import PID_FILE


def _parse_args():
    parser = argparse.ArgumentParser(
        prog="clipvault",
        description="Windows-style clipboard manager for Ubuntu",
    )
    parser.add_argument(
        "--version", action="version", version=f"ClipVault {__version__}"
    )
    return parser.parse_args()


def _write_pid():
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    log.info("pid file written: %s", PID_FILE)

    def _cleanup():
        log.info("normal shutdown, removing pid file %s", PID_FILE)
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except OSError:
            pass

    atexit.register(_cleanup)


def _install_signal_logging():
    """Log the signals that make the process disappear (systemd stop, Ctrl-C, logout)."""

    def _handler(signum, _frame):
        try:
            name = signal.strsignal(signum)
        except Exception:
            name = "?"
        log.warning("received signal %s (%s), exiting", signum, name)
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _handler)
        except (OSError, ValueError):
            pass


def main():
    _parse_args()
    diagnostics.log_environment()
    log.info("ClipVault %s starting", __version__)
    _write_pid()
    _install_signal_logging()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    diagnostics.install_qt_message_handler()
    diagnostics.install_signal_wakeup(app)
    app.setApplicationName("ClipVault")
    app.setQuitOnLastWindowClosed(False)

    history = HistoryManager()
    log.info("history loaded: %d item(s)", len(history.items))
    window  = ClipVaultWindow(history)
    tray    = TrayIcon(window, app)   # noqa: F841 — kept alive by reference
    app.aboutToQuit.connect(window.shutdown)

    # SIGUSR1 → toggle window (sent by the GNOME custom keybinding toggle script)
    def _on_sigusr1(*_):
        log.info("SIGUSR1 received -> toggle window")
        window._hotkey_activated.emit()

    signal.signal(signal.SIGUSR1, _on_sigusr1)

    window.show()
    log.info("entering Qt event loop")
    code = app.exec_()
    log.info("Qt event loop exited with code %s", code)
    sys.exit(code)


if __name__ == "__main__":
    main()
