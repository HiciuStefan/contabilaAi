import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contabila_ai.server.http import run


if __name__ == "__main__":
    host = os.environ.get("CONTABILA_AI_HOST", "127.0.0.1")
    port = int(os.environ.get("CONTABILA_AI_PORT", "8010"))
    run(host=host, port=port)
