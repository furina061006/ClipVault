"""Crash and behaviour diagnostics for ClipVault.

Everything is appended to a rotating log so that a crash which happens while
the app runs unattended can be diagnosed afterwards.

Log location:  ~/.local/state/clipvault/clipvault.log
Override with: CLIPVAULT_LOG_DIR=/some/dir

What it captures
----------------
* faulthandler: on SIGABRT/SIGSEGV/SIGBUS/SIGFPE/SIGILL (for example the
  glibc "double free or corruption" abort) the Python stack of EVERY thread is
  written to the log before the process dies.
* "kill -USR2 <pid>" dumps the stack of every thread on demand (useful to see
  what is stuck; SIGUSR1 is already used for the Super+V toggle).
* Uncaught exceptions in the main thread and in every Python/Qt thread.
* Qt's own warnings (qWarning/qCritical), which otherwise only reach journald.
"""

import faulthandler
import logging
import os
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.expanduser(os.environ.get("CLIPVAULT_LOG_DIR", "~/.local/state/clipvault"))
LOG_FILE = os.path.join(LOG_DIR, "clipvault.log")
# faulthandler writes to its own file: it keeps a raw file descriptor, so it
# cannot follow RotatingFileHandler's renames. Keeping it separate also bounds
# the normal log at maxBytes * (backupCount + 1) = ~8 MB.
CRASH_FILE = os.path.join(LOG_DIR, "crash.log")
_MAX_CRASH_FILE = 5 * 1024 * 1024

_fault_file = None          # kept alive for the whole process lifetime
_configured = False
_state = {}                 # keeps QSocketNotifier / pipe fds alive

_FMT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"


def _rotate_crash_file():
    """Keep crash.log bounded: one previous file is enough for post-mortem."""
    try:
        if os.path.getsize(CRASH_FILE) > _MAX_CRASH_FILE:
            os.replace(CRASH_FILE, CRASH_FILE + ".1")
    except OSError:
        pass


def get_logger() -> logging.Logger:
    return logging.getLogger("clipvault")


def setup(level: int = logging.INFO) -> logging.Logger:
    """Enable crash dumps and file logging. Safe to call more than once."""
    global _fault_file, _configured
    log = get_logger()
    if _configured:
        return log

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError as exc:  # read-only home etc. - never prevent startup
        print(f"clipvault: cannot create log dir {LOG_DIR}: {exc}", file=sys.stderr)
        return log

    log.setLevel(level)
    log.propagate = False
    formatter = logging.Formatter(_FMT)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    log.addHandler(stderr_handler)

    try:
        _rotate_crash_file()
        _fault_file = open(CRASH_FILE, "a", buffering=1, encoding="utf-8", errors="replace")
        _fault_file.write(
            "\n===== ClipVault start | pid=%d | %s =====\n"
            % (os.getpid(), time.strftime("%Y-%m-%d %H:%M:%S"))
        )
        _fault_file.flush()
        faulthandler.enable(file=_fault_file, all_threads=True)
        try:
            faulthandler.register(signal.SIGUSR2, file=_fault_file,
                                  all_threads=True, chain=False)
        except Exception:  # not fatal, only the on-demand dump is lost
            pass
    except Exception as exc:
        log.exception("could not enable faulthandler: %s", exc)

    threading.excepthook = _thread_excepthook
    sys.excepthook = _excepthook
    _configured = True
    log.info("diagnostics enabled (pid=%d, log=%s, crash_dump=%s)",
             os.getpid(), LOG_FILE, CRASH_FILE)
    return log


def _excepthook(exc_type, exc_value, exc_tb):
    get_logger().critical("uncaught exception in main thread",
                          exc_info=(exc_type, exc_value, exc_tb))
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _thread_excepthook(args):
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread else "?"
    get_logger().critical("uncaught exception in thread %s", name,
                          exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def install_signal_wakeup(app):
    """Make Python signal handlers run promptly inside the Qt event loop.

    Without this, SIGUSR1/SIGTERM are only handled the next time Python
    bytecode happens to execute, which may be never while the app is idle.
    A self-pipe + QSocketNotifier is the standard Qt/Python recipe.
    """
    if _state.get("notifier") is not None:
        return
    try:
        from PyQt5.QtCore import QSocketNotifier
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        os.set_blocking(write_fd, False)
        signal.set_wakeup_fd(write_fd)
        notifier = QSocketNotifier(read_fd, QSocketNotifier.Read)

        def _on_ready(fd):
            try:
                os.read(fd, 4096)
            except (BlockingIOError, OSError):
                pass
            # Returning into Python is what lets CPython dispatch the
            # pending signal handlers (SIGUSR1 toggle, SIGTERM logging, ...).

        notifier.activated.connect(_on_ready)
        _state["notifier"] = notifier
        _state["pipe"] = (read_fd, write_fd)
    except Exception:
        get_logger().exception("could not install signal wakeup notifier")


def install_qt_message_handler():
    """Route Qt (C++) warnings into our log file as well."""
    try:
        from PyQt5.QtCore import qInstallMessageHandler
    except Exception:
        return

    log = get_logger()

    def handler(mode, context, message):
        try:
            log.warning("qt: %s", message)
        except Exception:
            pass

    qInstallMessageHandler(handler)


def log_environment():
    log = get_logger()
    try:
        from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        log.info("python=%s qt=%s pyqt=%s",
                 sys.version.split()[0], QT_VERSION_STR, PYQT_VERSION_STR)
    except Exception:
        log.info("python=%s", sys.version.split()[0])
    log.info("display=%r wayland=%r session=%r",
             os.environ.get("DISPLAY"), os.environ.get("WAYLAND_DISPLAY"),
             os.environ.get("XDG_SESSION_TYPE"))
