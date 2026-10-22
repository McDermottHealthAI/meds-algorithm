import os
import subprocess

RUN_TIMEOUT = 5400


def run(cmd, *, timeout=RUN_TIMEOUT, env=None):
    result = subprocess.run(
        [str(value) for value in cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=None if env is None else {**os.environ, **env},
    )
    if result.returncode:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(map(str, cmd))}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return result
