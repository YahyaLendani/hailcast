# FlowSight Design System & Specification (Impeccable Operate Mode)

## Visual World: Obsidian Data Ops
FlowSight follows the **Operate** surface mode: high scanability, dense information hierarchy, restrained geometry, and mission-control ergonomics inspired by modern data engineering observability platforms (Datadog, Stripe Data, Grafana, Linear).

---

## Design Tokens & Palette

### Neutral Foundation
- **Canvas / Root Background**: `#080c14` (Deep obsidian dark space)
- **Panel / Surface 1**: `#0e1422` (Subtle elevation)
- **Surface 2 (Interactive)**: `#141d30`
- **Surface Hover**: `#1a263d`
- **Hairline Border**: `rgba(255, 255, 255, 0.08)` / `#1e293b`
- **Active Focus Ring**: `2px solid #34d399` with `1px outline-offset`

### Semantic Accents & Contrast Ratios (WCAG AA Compliant)
- **Streaming & Health (Emerald / Telemetry)**:
  - Primary / Highlight: `#34d399` (Emerald 400 — Contrast: >8.5:1 against `#080c14`)
  - Accent / Dim: `#059669` (Emerald 600)
  - Surface: `rgba(52, 211, 153, 0.15)`
  - Border: `rgba(52, 211, 153, 0.35)`
- **Machine Learning & Forecasting (Indigo / Predictive)**:
  - Primary / Highlight: `#818cf8` (Indigo 400 — Contrast: 6.2:1 against `#0e1422`)
  - Accent / Dim: `#4f46e5` (Indigo 600)
  - Surface: `rgba(129, 140, 248, 0.15)`
  - Border: `rgba(129, 140, 248, 0.35)`
- **Anomaly Monitoring (Amber / Alert)**:
  - Primary / Highlight: `#fbbf24` (Amber 400 — Contrast: 9.8:1 against `#080c14`)
  - Accent / Dim: `#d97706` (Amber 600)
  - Surface: `rgba(251, 191, 36, 0.15)`
  - Border: `rgba(251, 191, 36, 0.35)`

---

## Typography Ramp (Major Third 1.25x Progression)

FlowSight adheres to a strict geometric type ramp to eliminate flat-type hierarchies:

| Role | Size | Line Height | Weight | Usage |
| :--- | :--- | :--- | :--- | :--- |
| **KPI Readout (H1)** | `24px` (`1.5rem`) | `1.25` | Bold (`700`) | Top-level dashboard title & primary metric cards (`tabular-nums`) |
| **Section Header (H2)** | `19px` (`1.1875rem`) | `1.30` | Semibold (`600`) | View titles, primary chart headers |
| **Panel Header (H3)** | `15px` (`0.9375rem`) | `1.40` | Semibold (`600`) | Quality check tables, benchmark headers |
| **Body (Base)** | `14px` (`0.875rem`) | `1.50` | Regular (`400`) | General text, descriptions, table body |
| **Micro / Telemetry** | `12px` (`0.75rem`) | `1.40` | Medium (`500`) | Secondary metadata, labels, status tags |
| **Optical Floor** | `11px` (`0.6875rem`) | `1.20` | Semibold / Mono | Sub-labels, uppercase pill tags (Strict 11px floor) |

- **Tabular Numerics**: `num-tabular` (`font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;`) applied across all live counts, throughput rates, fares, and timestamps to prevent layout jitter during 50x event replay.

---

## Impeccable Mechanical Audit Compliance

FlowSight achieved a **0-defect score** on the Impeccable mechanical detector:
1. **De-nested Cards**: Eliminated cards-in-cards. Medallion progression strip runs in a single horizontal chassis with hairline vertical dividers (`divide-x`). Real-time feeds and anomaly lists are styled as flush divided rows (`divide-y`), eliminating nested containers.
2. **WCAG AA Contrast Calibration**: Purged low-contrast `text-slate-500` (4.1:1). All secondary text is upgraded to `text-slate-400` (7.3:1) and `text-slate-300`. Action buttons meet >10:1 contrast.
3. **Optical Floor**: Enforced an 11px floor. All micro-badges and tags use 11px or 12px with uppercase tracking, ensuring crisp rendering across high-DPI and standard monitors.
4. **Craft Floor Guarantees**:
   - Zero gradient text headings.
   - Zero eyebrow/kicker decorations.
   - Zero hard offset drop shadows; replaced with soft atmospheric elevation.
   - Fully themed browser scrollbars and focus rings.
