# Hailcast Design System

## Visual world: the transit line

Hailcast is an Operate surface: a dashboard read at a desk, in daylight, by data
engineers and people evaluating the system. The look borrows from printed transit
graphics (route diagrams, timetables, station signage), not from dark "mission
control" dashboards. One light theme, no theme switcher.

The signature is the pipeline drawn as a route line: Replay buffer, Stream, Bronze,
Silver, Gold are stations on one line with a lettered bullet each. The line shows a
moving dash only while the replay is running.

## Tokens

| Token | Value | Use |
| :--- | :--- | :--- |
| `--paper` | `#f3f0e8` | Page ground |
| `--surface` | `#fbfaf6` | Replay bar, chart surface |
| `--ink` | `#16150f` | Text, rules, signage band |
| `--ink-2` | `#454238` | Secondary text |
| `--ink-3` | `#676357` | Labels, hints (4.9:1 on paper) |
| `--rule` | `#d8d3c4` | Hairlines, grid lines |
| `--yellow` | `#f6b900` | Primary action, brand bullet, Gold tier. Fill only, never text |
| `--blue` | `#0b57d0` | Observed data, focus ring |
| `--orange` | `#b0480e` | Forecast series |
| `--ok` / `--alert` | `#1b6e45` / `#b42318` | Status only, always with a text label |
| `--bronze` / `--silver` | `#9a5a2c` / `#7b8089` | Tier bullets |

The chart pair (blue observed, orange forecast) passes the dataviz palette validator
on the light surface (colour-blind separation, contrast, chroma). Status colours are
never reused as series colours.

## Type

- **Schibsted Grotesk** for everything. Weights 400 to 800.
- **IBM Plex Mono** only for identifiers (event IDs, check names, feature names).
- Scale: body 15, labels and hints 13, section heading 20/700, figures 22/700,
  station counts 28/700, wordmark 24/800.
- Tabular numerals in table cells and the live feed only; display figures stay
  proportional.

## Layout

- Sections are separated by a 2px ink rule above the heading. No cards, no nested
  containers, no shadows.
- Signage band (ink) holds the wordmark, connection state and the replay clock.
- The replay bar is sticky and carries the only primary action. A yellow hairline
  along its bottom edge shows replay progress.
- Five tabs: Demand, Forecast, Anomalies, Data quality, Trips. The tab is kept in
  the URL hash.
- Under 900px the two-column splits stack; under 640px the route line turns
  vertical and the replay bar stops being sticky.

## Charts

- One y-axis per chart, zero-based, recessive grid, tooltips on hover.
- Demand: one blue bar per hour; hours containing a flagged zone are drawn in the
  alert colour and named in the legend.
- Forecast: observed (blue), forecast (orange), an 80% range band, and a dashed
  neutral reference for the typical hour. Legend sits above the plot in text ink.

## Copy

Plain labels, sentence case. Empty states say what to do next. The model verdict is
written from the real validation numbers and says so when a baseline wins.
