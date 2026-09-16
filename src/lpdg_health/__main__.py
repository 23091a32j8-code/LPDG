from __future__ import annotations

import argparse
from pathlib import Path

from .api import serve


parser = argparse.ArgumentParser(description="Run the offline LPDG gateway ranking API.")
parser.add_argument("--data", type=Path, default=Path("data"), help="Root of the mounted LPDG data bundle")
parser.add_argument("--output", type=Path, default=Path("runtime"), help="Directory for materialised predictions")
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()
serve(args.data, args.output, args.port)

