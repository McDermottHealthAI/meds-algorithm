import subprocess
import sys
import time

import pytest

from meds_algorithm_core.runtime.process import run


def test_run_preserves_output_and_failure():
    result = run([sys.executable, "-c", "print('ok')"])
    assert result.stdout.strip() == "ok" and result.returncode == 0
    with pytest.raises(AssertionError, match="bad"):
        run([sys.executable, "-c", "import sys; print('bad'); sys.exit(2)"])


def test_timeout_stops_descendant_work(tmp_path):
    ready, survived = tmp_path / "ready", tmp_path / "survived"
    child = (
        f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); "
        f"time.sleep(3); Path({str(survived)!r}).touch()"
    )
    parent = (
        f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(10)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, "-c", parent], timeout=2)
    assert ready.exists(), "child must have started before timeout"
    time.sleep(2)
    assert not survived.exists(), "descendant continued executing after timeout"
