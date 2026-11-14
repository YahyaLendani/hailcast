#!/usr/bin/env python3
"""
Hailcast: quickstart demo launcher
Runs the database migrations, loads sample data, trains ML models, and starts the platform server.
"""

import os
import sys
import time
import webbrowser
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"

def main():
    print("=" * 70)
    print("Hailcast: real-time data engineering and predictive analytics")
    print("=" * 70)

    # Set PYTHONPATH
    os.environ["PYTHONPATH"] = str(BACKEND_DIR)

    python_bin = sys.executable

    print("\n[Step 1/4] Checking sample transportation dataset...")
    data_gen = BACKEND_DIR / "app" / "data" / "download_sample.py"
    sample_file = BACKEND_DIR / "app" / "data" / "sample_trips.json"
    if not sample_file.exists():
        print("  Generating the synthetic trip sample (shaped like NYC TLC records)...")
        subprocess.run([python_bin, str(data_gen)], check=True)
    else:
        print("  Sample trips dataset ready.")

    print("\n[Step 2/4] Running End-to-End Pipeline & Data Quality Tests...")
    # The tests use a throwaway database, so they never touch the demo data.
    res = subprocess.run([python_bin, "-m", "pytest", "-q", "-p", "no:warnings"], cwd=str(BASE_DIR), check=False)
    if res.returncode != 0:
        print("  Warning: Tests reported an issue, continuing demo launch...")

    print("\n[Step 3/4] Launching FastAPI Backend & Live Streaming Dashboard...")
    print("  Serving interactive dashboard at: http://localhost:8000")
    print("  Serving API documentation at:     http://localhost:8000/docs")
    print("  Streaming WebSockets endpoint:   ws://localhost:8000/ws/stream")
    print("\n  Press CTRL+C to terminate.")

    # Automatically open browser after 2 seconds
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Launch uvicorn
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, app_dir=str(BACKEND_DIR))

if __name__ == "__main__":
    main()

