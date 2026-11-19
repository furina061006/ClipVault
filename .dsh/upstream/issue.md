# Intermittent SIGABRT: `double free or corruption (fasttop)` — clipboard is polled from a QThread

## Environment

- Ubuntu 22.04.5, **X11** session (GNOME, XWayland not involved)
- Python 3.10.12
- PyQt5 5.15.11 (bundled Qt 5.15.19), pynput 1.8.2, Pillow 9.0.1
- clipvault **1.0.6** installed from PyPI
- started as a systemd user service with `Restart=on-failure`, `RestartSec=3`

## Symptom

The process disappears every few minutes to a few hours, then systemd brings it
back. It is not OOM and not SIGKILL; it aborts with SIGABRT.

`journalctl --user -u clipvault`:

```
clipvault[24846]: double free or corruption (fasttop)
clipvault.service: Main process exited, code=dumped, status=6/ABRT
clipvault.service: Failed with result 'core-dump'.
clipvault.service: Consumed 12.160s CPU time.
```

Three consecutive crashes on one day: 04:29:47, 04:45:10, 04:49:49
(2m31s / 15m19s / 4m36s after start). `/var/log/apport.log` has 20 entries for
this executable, **all `signal 6`**, going back two days. `dmesg` shows no OOM
killer activity.

So this is glibc heap corruption inside the process, not the OS killing it.

## Likely cause

`ClipboardWatcher` is a `QThread` and its `run()` calls, from the worker
thread:

```python
app = QApplication.instance()
cb = app.clipboard()
mime = cb.mimeData()
...
img = cb.image()
ba = img.bits()
ba.setsize(img.byteCount())
pil = Image.frombytes("RGBA", ...)
```

`QClipboard`, `QImage` and the platform clipboard backend are GUI objects and
must only be used from the thread that owns the GUI. On X11, touching them from
a `QThread` is undefined behaviour and can corrupt the allocator — which matches
the `double free` abort.

Two smaller issues in the same loop:

- the image is always decoded as `RGBA`, regardless of `img.format()`
  (also `byteCount()` is deprecated);
- every exception is swallowed by `except Exception: pass`, so failures are
  invisible.

## Reproduction

Not reliably reproducible. I stress-tested text copies, image copies, window
toggling and simulated pastes for ~30 minutes without a crash; in normal use it
died within 2–15 minutes. The crash timing looks random, which fits a data race.

## Proposed fix

I have a PR that moves the polling into the GUI thread
(`QObject` + `QTimer`, image re-read throttled, 16×16 fingerprint to avoid
re-encoding unchanged images, RGBA8888 normalisation, clean shutdown).
Happy to split it or adjust the approach.

```
# PR: <link>
```
