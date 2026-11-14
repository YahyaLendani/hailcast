# Hailcast Product Specification

## Mission & Purpose
Hailcast is a real-time data engineering, event replay, and predictive analytics platform for urban transportation and mobility intelligence. It demonstrates the complete lifecycle of a mission-critical distributed data system: high-throughput stream ingestion, deterministic deduplication, Medallion data tiering (Bronze -> Silver -> Gold), time-aware machine learning demand forecasting, unsupervised anomaly detection, and operational monitoring.

## Target User & Surface Mode
- **Surface Mode**: **Operate** (Production analytics dashboard, mission control, pipeline monitoring, ML workbench).
- **Core User Persona**: Data Engineers, MLOps Engineers, Analytics Directors, and Technical Recruiters evaluating end-to-end data systems.
- **Success Criteria**:
  - Instant scanability of pipeline health, throughput (EPS), and queue depth.
  - Frictionless control of historical event replay at variable velocities ($1\times \dots 50\times$).
  - Transparent ML model evaluation with guaranteed zero future-data leakage.
  - Sub-second feedback during streaming ingestion and live chart updates.


## Primary user: the taxi dispatcher
The first screen ("Where to go") answers one question for a fleet dispatcher or driver:
which pickup zones will be busiest in the next 1, 3 or 6 hours, and what they are worth.
It ranks zones by expected pickups or expected takings, using the city-wide forecast split
by each zone's usual share at that hour. Engineers find the pipeline, forecast evaluation
and data-quality views in the side navigation.
