"""Production entrypoint for Render and cloud hosts.

Starts the LiveKit voice agent worker in the background and runs the HTTP
token server in the foreground on the assigned $PORT.
"""

from __future__ import annotations

import signal
import subprocess
import sys


def run() -> None:
    # 1. Start the LiveKit worker process in background
    worker_proc = subprocess.Popen([sys.executable, "-m", "roxstar.worker", "start"])

    def cleanup(_sig: int, _frame: object) -> None:
        worker_proc.terminate()
        try:
            worker_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker_proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # 2. Run the HTTP token server in the foreground
    from roxstar.token_server import main as run_token_server

    try:
        run_token_server()
    finally:
        worker_proc.terminate()


if __name__ == "__main__":
    run()
