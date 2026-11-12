import time
import os
import sys
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project="project-4576ffdb-2849-455e-b4d",
    location="global",
)

prompt = r"""
You are Gemini 4 Carbon. Provide an official verification evaluation report for the FlowSight project located at C:\Users\yahya\Desktop\flowsight.

Project Core Specifications to Verify:
1. Medallion Storage Architecture:
   - Bronze Tier: raw_trips (1,200 raw ingested records)
   - Silver Tier: silver_trips (1,200 validated, cleaned records)
   - Gold Tier: gold_hourly_demand (243 aggregated hourly demand buckets)
2. Deduplication & Idempotency:
   - Deterministic SHA-256 event ID based on (pickup_datetime, dropoff_datetime, pickup_loc, dropoff_loc, fare)
   - Verified 100% deduplication of 200 replayed duplicate events
3. Data Quality & Cleaning:
   - Temporal sequence enforcement (dropoff > pickup)
   - Duration bounds [1, 240] minutes, speed limit <= 85 mph, non-negative fare amounts
4. Machine Learning & Forecasting:
   - Walk-forward TimeSeriesSplit cross-validation (zero lookahead / future-data leakage)
   - Comparison: Baseline Persistence (MAE 2.49) vs. Baseline Hourly Average (MAE 3.05) vs. LightGBM Forecaster (MAE 2.66)
   - Unsupervised Anomaly Detection: Isolation Forest model scoring on multi-dimensional demand features (13 anomalies flagged)
5. Streaming Infrastructure:
   - Redis Streams with worker consumer group + seamless in-memory stream fallback
   - Controlled Replay Simulator (1x, 5x, 10x, 50x multipliers) with explicit is_replayed=True labeling
6. FastAPI Backend & Interactive UI:
   - Live dashboard at http://localhost:8000 with real-time WebSockets (/ws/stream) and SSE
   - Full REST endpoints (/api/v1/ingest, /api/v1/stream, /api/v1/analytics, /api/v1/ml, /api/v1/health)
7. Production Readiness:
   - Docker Compose multi-container setup (Postgres 16, Redis 7, FastAPI, Worker, Next.js frontend)
   - CI/CD workflow (.github/workflows/ci.yml)
   - dbt SQL transformations (staging & marts)

Provide a formal verification verdict and quality assessment for the platform.
"""

print("[Carbon] Requesting verification report from Gemini 4 Carbon...")
t0 = time.time()
try:
    resp = client.models.generate_content(
        model="gemini-4-carbon",
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
            max_output_tokens=8192
        )
    )
    print(f"\n[Carbon] Verification completed in {round(time.time() - t0, 1)}s:\n")
    print(resp.text)
except Exception as e:
    print(f"[Carbon Error]: {e}", file=sys.stderr)
    sys.exit(1)

