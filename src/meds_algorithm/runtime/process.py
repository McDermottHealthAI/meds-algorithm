import os
import signal
import subprocess
import threading
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path

RUN_TIMEOUT = 5400


@contextmanager
def _raise_on_termination():
    """Turn SIGTERM/SIGHUP into SystemExit while waiting, so the owned group is still stopped.

    Python otherwise exits on these signals without unwinding, leaving the group running (for example when
    an outer `timeout` or a closed terminal ends pytest). Inherited non-default handlers are kept.
    """
    signals = (signal.SIGTERM, signal.SIGHUP) if os.name == "posix" else ()
    if threading.current_thread() is not threading.main_thread():
        signals = ()

    def stop(signum, frame):
        raise SystemExit(128 + signum)

    previous = {s: signal.getsignal(s) for s in signals}
    for s, handler in previous.items():
        if handler is signal.SIG_DFL:
            signal.signal(s, stop)
    try:
        yield
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def run(cmd, *, timeout=RUN_TIMEOUT, env=None, cwd=None, log_path=None):
    """Run in an owned process group and stop its descendants if interrupted, terminated or timed out.

    Descendants must remain in the group; deliberately detached services are not supported.
    Windows uses taskkill /T to terminate the child tree while the parent is still alive.
    """
    with ExitStack() as stack:
        stack.enter_context(_raise_on_termination())
        log = stack.enter_context(Path(log_path).open("w", encoding="utf-8")) if log_path else None
        process = subprocess.Popen(
            [str(value) for value in cmd],
            stdout=log if log is not None else subprocess.PIPE,
            stderr=subprocess.STDOUT if log is not None else subprocess.PIPE,
            text=True,
            cwd=cwd,
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
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
            raise
        result = subprocess.CompletedProcess(process.args, process.returncode, stdout or "", stderr or "")
        if result.returncode:
            raise AssertionError(
                f"command failed ({result.returncode}): {' '.join(map(str, cmd))}\n"
                f"Log: {log_path}\n"
                f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
            )
        return result
