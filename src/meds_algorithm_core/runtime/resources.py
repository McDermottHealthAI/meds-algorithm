from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

try:
    import resource
except ImportError:
    resource = None


def _rss_bytes(value: int) -> int:
    # Linux reports KiB; macOS reports bytes. sys.platform is deliberately avoided so unusual Unix
    # implementations can override/report their method rather than receiving a false portable claim.
    return value * 1024 if sys.platform != "darwin" else value


class _ProcessTreeMemorySampler:
    """Sample aggregate PSS/RSS for this process and its live descendants on Linux."""

    def __init__(self, interval_seconds: float = 0.25) -> None:
        self.interval_seconds = interval_seconds
        self.peak_pss_bytes: int | None = None
        self.peak_rss_bytes: int | None = None
        self.source = "linux_proc_smaps_rollup" if Path("/proc/self/smaps_rollup").is_file() else "getrusage"
        self.includes_descendants = self.source == "linux_proc_smaps_rollup"
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="meds-memory-sampler", daemon=True)

    def start(self) -> None:
        self._sample()
        self._thread.start()

    def stop(self) -> None:
        self._sample()
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds * 4))
        self._sample()
        if self.peak_rss_bytes is None:
            self.includes_descendants = False
            if resource is not None:
                self.source = "getrusage"
                usage = resource.getrusage(resource.RUSAGE_SELF)
                self.peak_rss_bytes = _rss_bytes(usage.ru_maxrss)
            else:
                self.source = "unavailable"

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()

    @staticmethod
    def _process_tree(root_pid: int) -> set[int]:
        found: set[int] = set()
        pending = [root_pid]
        while pending:
            pid = pending.pop()
            if pid in found:
                continue
            found.add(pid)
            try:
                tasks = list(Path(f"/proc/{pid}/task").iterdir())
            except OSError:
                continue
            for task in tasks:
                try:
                    pending.extend(int(value) for value in (task / "children").read_text().split())
                except (OSError, ValueError):
                    continue
        return found

    @staticmethod
    def _smaps(pid: int) -> tuple[int, int] | None:
        try:
            values = {}
            for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
                key, separator, rest = line.partition(":")
                if separator and key in {"Pss", "Rss"}:
                    values[key] = int(rest.split()[0]) * 1024
            return values["Pss"], values["Rss"]
        except (FileNotFoundError, KeyError, PermissionError, ProcessLookupError, ValueError):
            return None

    def _sample(self) -> None:
        if self.source != "linux_proc_smaps_rollup":
            return
        samples = [sample for pid in self._process_tree(os.getpid()) if (sample := self._smaps(pid))]
        if not samples:
            return
        if len(samples) != len(self._process_tree(os.getpid())):
            self.includes_descendants = False
        pss = sum(sample[0] for sample in samples)
        rss = sum(sample[1] for sample in samples)
        self.peak_pss_bytes = max(self.peak_pss_bytes or 0, pss)
        self.peak_rss_bytes = max(self.peak_rss_bytes or 0, rss)
