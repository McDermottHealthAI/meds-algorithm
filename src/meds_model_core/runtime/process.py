import os
import signal
import subprocess
from contextlib import suppress

RUN_TIMEOUT = 5400


def run(cmd, *, timeout=RUN_TIMEOUT, env=None):
    """Run in an owned process group and stop its descendants if interrupted or timed out.

    Descendants must remain in the group; deliberately detached services are not supported.
    Windows uses taskkill /T to terminate the child tree while the parent is still alive.
    """
    process = subprocess.Popen(
        [str(value) for value in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=os.name == "posix",
        env=None if env is None else {**os.environ, **env},
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        try:
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            process.stderr.close()
        raise
    result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    if result.returncode:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(map(str, cmd))}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return result
