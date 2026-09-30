"""Start the JusticeFlow API:  python backend/run.py  [--port 8000] [--reload]

Works from any folder. If the port is already taken it says whether that is a
JusticeFlow backend that is already running (so there is nothing to do) or some
other program, instead of failing with a raw socket error.
"""

import argparse
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def is_justiceflow(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=2) as r:
            return json.load(r).get("status") == "ok"
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true", help="restart automatically when code changes")
    args = ap.parse_args()

    if port_in_use(args.host, args.port):
        if is_justiceflow(args.host, args.port):
            print(f"The JusticeFlow backend is already running at http://{args.host}:{args.port} - nothing to do.\n"
                  f"To restart it, close the terminal (or stop the process) that started it, then run this again.")
            return 0
        print(f"Port {args.port} is used by another program. Start on a different port, e.g.:\n"
              f"  python {Path(__file__).name} --port 8001\n"
              f"and change the /api proxy target in frontend/vite.config.ts to match.")
        return 1

    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    if not (BACKEND / "justiceflow.db").exists() and "DATABASE_URL" not in os.environ:
        print("No database yet. Load demo data first:  python -m app.seed   (from the backend folder)")
        return 1

    import uvicorn
    print(f"JusticeFlow API on http://{args.host}:{args.port}  (docs: /docs)")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
