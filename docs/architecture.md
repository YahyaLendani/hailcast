# Hailcast Architecture & System Design

Hailcast is a data engineering and predictive analytics platform engineered to demonstrate the end-to-end lifecycle of a modern streaming and analytical data system.

```mermaid
flowchart TD
    subgraph INGESTION ["1. Ingestion Layer"]
        A1[Synthetic trip sample, TLC-shaped] -->|Controlled Replay| B1[Replay Engine]
        A2[External Clients / APIs] -->|Batch Upload| B2[FastAPI Ingestion Endpoint]
        B1 -->|Replayed Events| C1[Redis Streams]
        B2 -->|Batch Payloads| C2[ETL Batch Pipeline]
    end

    subgraph STREAMING ["2. Streaming & Processing Layer"]
        C1 -->|Consumer Group / XREADGROUP| D1[Asynchronous Streaming Worker]
        D1 -->|Idempotency Check| E1[Deduplication Engine]
        E1 -->|Validation Checks| F1[Data Cleaning & Quality Service]
    end

    subgraph STORAGE ["3. Medallion Storage Tier (PostgreSQL / SQLite)"]
        F1 -->|Raw Immutable Log| G1[(Bronze: raw_trips)]
        F1 -->|Cleaned & Enriched| G2[(Silver: silver_trips)]
        G2 -->|SQL Transformations & Rollups| G3[(Gold: gold_hourly_demand)]
    end

    subgraph ML ["4. Machine Learning & Forecasting"]
        G3 -->|Walk-Forward TimeSeriesSplit| H1[Feature Engineering]
        H1 -->|Cyclical & Causal Lags| H2[LightGBM Demand Forecaster]
        H1 -->|Previous Hour, Same Hour Yesterday, Hour-of-Day Average| H3[Baseline Models]
        H1 -->|Multi-Dimensional Outliers| H4[Isolation Forest Anomaly Detector]
        H2 -->|Model Weights & Metrics| I1[Experiment Tracker & Model Registry]
    end

    subgraph SERVING ["5. Serving & Real-Time Visualization"]
        G3 --> J1[FastAPI Analytics Endpoints]
        H2 --> J2[Forecasting API]
        H4 --> J3[Anomaly Alerts API]
        D1 -->|Live Push| K1[WebSocket & SSE Broadcaster]
        J1 --> L1[Next.js & Interactive Analytics Dashboard]
        J2 --> L1
        J3 --> L1
        K1 --> L1
    end
```

## Medallion Architecture Breakdown

### 1. Bronze Tier (`raw_trips`)
- **Nature**: Append-only, immutable event log.
- **Fields**: Deterministic `event_id`, timestamps, locations, raw fares, and `is_replayed` boolean flag.
- **Purpose**: High-throughput ingestion preserving source fidelity for auditability and historical replay.

### 2. Silver Tier (`silver_trips`)
- **Nature**: Cleaned, deduplicated, enriched operational records.
- **Transformations**:
  - Filter invalid temporal sequences (`dropoff <= pickup`).
  - Outlier filtering (duration outside 1–240 minutes, speed exceeding 85 mph, non-positive fares).
  - Feature derivation: `trip_duration_minutes`, `speed_mph`.
- **Purpose**: Reliable, sanitized ground truth for downstream modeling and business analytics.

### 3. Gold Tier (`gold_hourly_demand`)
- **Nature**: Pre-aggregated hourly analytical tables.
- **Aggregations**: `trip_count`, `total_passengers`, `avg_fare`, `avg_distance`, `total_revenue`, `avg_duration_minutes`.
- **Enrichments**: `anomaly_score`, `is_anomaly` flags populated by the Isolation Forest detector.
- **Purpose**: Sub-millisecond dashboard queries and high-velocity model feature stores.

---

## Controlled Replay Engine & Data Integrity

- **Simulated Real-Time Streaming**: Historical trip events are read in chronological order and replayed through Redis Streams at customizable speed factors ($1\times, 5\times, 10\times, 50\times$).
- **Strict Labeling**: Every replayed record is marked with `is_replayed = True` to fulfill strict regulatory and data requirement transparency.
- **Idempotent Deduplication**: Each event generates a deterministic hash `event_id = SHA256(pickup_datetime, dropoff_datetime, pickup_location, dropoff_location, fare)`. Any re-delivered or re-played duplicate event is rejected before entering the Silver tier.

