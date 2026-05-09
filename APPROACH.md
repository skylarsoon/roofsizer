# PitchPoint Approach

## Problem

Roofing contractors need fast, trustworthy roof measurements before they can prepare a quote. Traditional measurement reports can slow down the sales process. PitchPoint turns backend accuracy outputs into a polished product experience: address in, roof measured, quote ready.

## Why Address-First

Contractors think in properties, not files or model runs. The frontend should start with an address, then load the relevant prediction artifacts from the backend pipeline when they exist.

## Accuracy Boundary

The product shell consumes measurement artifacts. It does not change scenario logic, pitch logic, building selection logic, scoring logic, benchmark calculations, or address-specific behavior.

Expected artifacts include:

- `prediction.json`
- `satellite.png`
- `selected.geojson`
- `top_candidates.geojson`
- `leaderboard.csv`
- `scenario_summary.csv`
- `dataset_summary.csv`
- `summary.md`
- `pattern_analysis.md`
- `recommended_scenario.md`
- `submission.json`

Missing artifacts should produce friendly empty states, not crashes.

## Measurement Model

The core measurement relationship is:

```text
Roof Sqft = Footprint Sqft × Pitch Multiplier
```

PitchPoint should explain this formula in the UI and report, but the source values should come from the accuracy pipeline.

## Quote Preview

PitchPoint can turn predicted roof sqft into a preliminary estimate preview. The quote is not a replacement for professional review.

Typical derived values:

- Roofing squares: `predicted_sqft / 100`
- Billable squares: roofing squares plus waste
- Estimated low/high: billable squares multiplied by configured price-per-square ranges

## Customer Report

The customer report should be trustworthy, readable, and contractor-friendly. It should include:

- Property address
- Predicted roof sqft
- Footprint sqft when available
- Pitch and pitch multiplier
- Confidence
- Manual review flag
- Warnings
- Satellite image
- Overlay image when available
- Estimate preview
- Assumptions and disclaimer

## Accuracy Lab

The demo should also show engineering discipline. When benchmark files exist, PitchPoint should surface:

- Recommended scenario
- Leaderboard
- Scenario summary
- Dataset summary
- Worst cases
- Pattern analysis
- Decision log

This is how the team shows that the result was measured and iterated, not guessed.

## What We Tried

Current frontend work focuses on the customer demo layer: refined split-screen UI, mock analysis flow, animated roof polygon, metric cards, line items, estimate bar, address autocomplete, typewriter math, and completion toast.

Backend accuracy and artifact generation are expected to continue in parallel.

## Final Scenario Selection

Final scenario selection should come from benchmark artifacts such as `recommended_scenario.md`, `leaderboard.csv`, and `scenario_summary.csv`. PitchPoint should display the selected scenario and supporting metrics, not pick or rank scenarios itself.

## Future Improvements

- Replace mock frontend results with a FastAPI endpoint backed by `prediction.json`.
- Display real `satellite.png` and `overlay_selected.png`.
- Add customer report viewing/export from generated `report.html`.
- Add Accuracy Lab and Submission Outputs screens.
- Add validation CSV status once the backend data-quality script exists.
