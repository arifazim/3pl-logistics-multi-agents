#!/usr/bin/env python3
"""Cloud Run entrypoint — binds to $PORT (default 8080)."""

import os
import sys
from pathlib import Path

# Ensure project root is on the path when running inside the container
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn

PORT = int(os.getenv("PORT", "8080"))

if __name__ == "__main__":
    print(f"[entrypoint] Starting 3PL dashboard on port {PORT}")
    uvicorn.run(
        "frontend.cloudrun_app.app:app",
        host="0.0.0.0",
        port=PORT,
        workers=1,
        log_level="info",
    )
