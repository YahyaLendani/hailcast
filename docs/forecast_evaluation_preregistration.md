# Does LightGBM beat honest baselines? Plan fixed before the corrected evaluation is run

Written 2026-11-15, before any code is changed and before the corrected evaluation exists.

## Why this exists

The current report says LightGBM has the lowest error. A review found two problems with that:

1. The baseline labelled "average for that hour of day" looks up the pair (day of week, hour). With
   seven days of data, no test hour's pair ever appears in its training window (0 of 41 in each fold).
   So it always predicts the overall training mean.
2. The standard baseline for a daily cycle, "same hour yesterday", is missing.

**This plan is not blind.** A read-only probe on the current code, with the current features,
already gave these mean MAEs over the three folds: same hour yesterday 12.85, LightGBM 13.30, true
hour-of-day average 15.07, previous hour 20.11. The rules below are fixed now so that the corrected
run is judged by them and not by what looks best afterwards.

## Question

On this synthetic data, one hour ahead and city-wide, does LightGBM forecast hourly demand better
than the strongest simple baseline?

## Setup (fixed now)

- **Data:** `backend/app/data/sample_trips.json` as committed (seed 42), loaded through the batch
  pipeline as `generate_reports.py` does now. The series is city-wide trips per hour, with the
  newest hour dropped (167 hours, 2026-11-01 00:00 to 2026-11-07 22:00).
- **No back-filled features:** `bfill()` is removed from feature building. The first 24 hours are
  dropped, because they have no complete `lag_24h` or 24-hour rolling mean. That leaves 143 hours.
  No other feature changes.
- **Folds:** `TimeSeriesSplit(n_splits=3)` on those 143 hours: training windows of 38, 73 and 108
  hours, each followed by a 35-hour test window. Together the three test windows form one continuous
  105-hour stretch.
- **LightGBM:** the hyperparameters in `backend/app/ml/models.py` as committed, `random_state=42`.
  No tuning, no feature selection and no reruns after the results are seen.
- **Baselines** (each fitted on the training window only, where it needs fitting):
  - **Previous hour:** `lag_1h`.
  - **Same hour yesterday:** `lag_24h`.
  - **Hour-of-day average:** the mean demand for each hour 0 to 23 in the training window, ignoring
    day of week. It replaces the current (day of week, hour) baseline, which cannot work on seven
    days. The dashboard's baseline line switches to it too.

## Measures

- **Headline:** MAE in trips per hour, pooled over the 105 test hours.
- **Comparator:** the baseline with the lowest pooled MAE. Picking the strongest one after the run is
  deliberately the harder test for LightGBM.
- **Decision statistic:** the mean paired difference d = |LightGBM error| − |comparator error| over
  the 105 hours, with a 95% interval from a moving block bootstrap (blocks of 24 consecutive hours,
  2000 resamples, seed 0). Blocks are used because neighbouring hours are correlated.
- **Reported, not deciding:** RMSE, MAPE (hours with demand above zero), R², MAE per fold for every
  model, and how many folds LightGBM wins.

## Decision rule

1. **Upper bound of d below 0:** LightGBM beats the strongest baseline. The README may say so, with
   the size of the gap.
2. **Lower bound of d above 0:** the baseline beats LightGBM. The README says so plainly, and names
   the baseline.
3. **Otherwise:** no measurable difference on this data. The README says LightGBM is not shown to
   beat the strongest baseline.

Whichever way it goes, the README table and `docs/ml_evaluation_report.md` are regenerated from the
run and nothing is reworded to soften it.

## Validity rules

- The leakage test is extended to change demand at the very first hour too. It must pass before the
  evaluation is run.
- If the corrected pipeline cannot produce exactly 143 hours and three 35-hour test windows, the
  run is reported as invalid and the rule is not applied until the cause is fixed and this plan is
  amended in a dated note.
- 105 test hours of synthetic data is a small sample. Whatever the result, it says something about
  this generator, not about real New York demand. The generator (`download_sample.py`) is a fixed
  daily curve plus ±15% noise, which favours "same hour yesterday" by construction.
- The multi-hour dashboard forecast and the anomaly detector are out of scope.

## Order of work

1. Commit this plan alone.
2. Fix the features and baselines, extend the leakage test, and add the block-bootstrap comparison
   to `generate_reports.py`. Commit.
3. Run `python -m pytest`, then `python backend/scripts/generate_reports.py`, once. Update the README
   from the generated report. Commit.
