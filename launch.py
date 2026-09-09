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

ROOT = Path(__file__).resolve().parent
APP_ID = "taiwan-market-lens-0908"


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
    ports = range(8501, 8511)
    for port in ports:
        if is_our_app(port):
            return port, True
    for port in ports:
        if port_free(port):
            return port, False
    raise RuntimeError("Ports 8501-8510 are all busy. Close an unused server and retry.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="Report the port without starting a server.")
    args = parser.parse_args()
    port, reuse = select_port()
    url = f"http://127.0.0.1:{port}"
    if args.check:
        print(f"{'REUSE' if reuse else 'START'} {url}")
        return 0
    if reuse:
        print(f"Dashboard is already running. Opening {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    print(f"Starting Taiwan Market Lens at {url}", flush=True)
    if port != 8501:
        print(f"Port 8501 is occupied by another service; using {port}.", flush=True)
    print("Keep this window open. Press Ctrl+C to stop.", flush=True)
    process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
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
