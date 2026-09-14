"""Idempotent local launcher: reuse this app, avoid unrelated occupied ports."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
APP_ID = "taiwan-market-lens-0908"
PORTS = range(8501, 8511)


def is_our_app(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/app/static/app-id.json", timeout=0.5) as response:
            return json.load(response).get("app") == APP_ID
    except Exception:
        return False


def port_free(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def select_port():
    for port in PORTS:
        if is_our_app(port):
            return port, True
    for port in PORTS:
        if port_free(port):
            return port, False
    raise RuntimeError("Ports 8501-8510 are all busy. Close an unused server and retry.")


def listening_pids():
    """Port -> PID for every local TCP listener, from a single netstat call.

    The state column is skipped on purpose: it is localised on some Windows
    installs, whereas a listener's foreign address is always the wildcard.
    """
    try:
        listing = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                                 text=True, errors="replace", timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    pids = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[2] not in ("0.0.0.0:0", "[::]:0"):
            continue
        try:
            port, pid = int(parts[1].rsplit(":", 1)[1]), int(parts[4])
        except (ValueError, IndexError):
            continue
        if pid:
            pids.setdefault(port, pid)
    return pids


def stop_dashboards():
    """Stop every dashboard of ours that is listening, so a restart is a real one.

    Only ports that answer with our app id are touched, so an unrelated service
    on 8501-8510 is never killed. Returns the ports stopped and the ones that
    resisted; the caller is expected to give up rather than start a second copy.
    """
    owners = listening_pids()
    stopped, failed = [], []
    for port in PORTS:
        if not is_our_app(port):
            continue
        pid = owners.get(port)
        if pid is None:
            failed.append((port, "the port answers but no process admits to owning it"))
            continue
        killed = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                capture_output=True, text=True, errors="replace")
        if killed.returncode:
            failed.append((port, (killed.stderr or killed.stdout).strip()))
        else:
            stopped.append(port)
    for port in stopped:
        for _ in range(40):
            if port_free(port):
                break
            time.sleep(.25)
    return stopped, failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="Report the port without starting a server.")
    parser.add_argument("--restart", action="store_true",
                        help="Stop a dashboard that is already running instead of reusing it.")
    args = parser.parse_args()
    if args.check:
        port, reuse = select_port()
        print(f"{'REUSE' if reuse else 'START'} http://127.0.0.1:{port}")
        return 0
    if args.restart:
        stopped, failed = stop_dashboards()
        for port, reason in failed:
            print(f"Could not stop the dashboard on port {port}: {reason}", file=sys.stderr)
        if failed:
            print("Nothing was restarted; close that window yourself and run this again.", file=sys.stderr)
            return 1
        for port in stopped:
            print(f"Stopped the dashboard already running on port {port}.", flush=True)
    port, reuse = select_port()
    url = f"http://127.0.0.1:{port}"
    if reuse:
        print(f"Dashboard is already running. Opening {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    print(f"Starting Taiwan Market Lens at {url}", flush=True)
    if port != 8501:
        print(f"Port 8501 is occupied by another service; using {port}.", flush=True)
    print("Keep this window open. Press Ctrl+C to stop.", flush=True)
    process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/streamlit_app.py",
                                "--server.address", "127.0.0.1", "--server.port", str(port),
                                "--server.headless", "true"], cwd=ROOT)
    try:
        for _ in range(120):
            if process.poll() is not None:
                return process.returncode or 1
            if is_our_app(port):
                if not args.no_browser:
                    webbrowser.open(url)
                return process.wait()
            time.sleep(.25)
        print("Startup timed out. See the server output above.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
