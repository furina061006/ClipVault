# Fix: poll the clipboard on the GUI thread

Fixes the intermittent `SIGABRT` (`double free or corruption (fasttop)`)
reported in #<issue-number>.

## Why

`ClipboardWatcher` inherited from `QThread` and called `QApplication.clipboard()`,
`mimeData()`, `image()` and `QImage` accessors from that worker thread. These are
GUI objects; on X11 they may only be used from the GUI thread, and using them
from another thread is undefined behaviour that can corrupt the heap.

## What changed

- `ClipboardWatcher` is now a `QObject` + `QTimer` created by `ClipVaultWindow`,
  i.e. it runs on the GUI thread. No clipboard call leaves that thread.
- **Text** is polled every 500 ms (`mimeData()` + `text()`, well under 1 ms).
- **Images** are expensive (`QClipboard.image()` on a 2560×1440 image costs
  ~180 ms because the owner has to re-serve the data), so they are only read
  when the MIME format list changes, or at most every 5 s. A 16×16 downscale
  fingerprint decides whether the full PNG encoding is needed at all.
- Image data is normalised with `convertToFormat(QImage.Format_RGBA8888)` and
  `sizeInBytes()` before being passed to Pillow.
- The timer is stopped on `app.aboutToQuit` (`ClipVaultWindow.shutdown`).
- Tests updated for the new design.

## Behaviour notes

- Text capture latency is unchanged (~0.5 s).
- If two different images keep the exact same format list, capture may be
  delayed by up to 5 s. Chosen deliberately to keep the GUI responsive.
- CPU use in the background drops noticeably: the old loop re-read and
  re-encoded a static image every 0.5 s.

## Tests

```
$ python3 -m pytest app/tests/test_clipboard_watcher.py -q
9 passed
```

I also verified on a live X11 session: text and image capture work, Super+V /
SIGUSR1 toggling still works, and a static 2560×1440 image for 20 s costs
< 1 s of CPU.
