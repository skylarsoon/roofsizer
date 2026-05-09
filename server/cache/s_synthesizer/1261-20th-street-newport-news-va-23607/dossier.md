# Roof pitch evidence dossier

**Address:** 1261 20th Street, Newport News, VA 23607
**Geocoded:** 36.98456, -76.40165

## Candidate pitch estimates

| Method | Rise/12 | Multiplier | Confidence | Source | Reasoning |
|---|---:|---:|---:|---|---|
| regional | 6:12 | 1.1180 | 0.65 | `regional_default` |  |
| streetview | 4:12 | 1.0541 | 0.75 | `streetview` | The main roof is clearly visible side-on with a shallow gable slope, around 18 degrees from horizontal. |
| gpt_multi | 4:12 | 1.0541 | 0.70 | `llm_multi` | The complex hipped roof massing, minimal ridge shadow, and wide visible roof planes point to a shallow roughly 4:12 pitch.; The complex low hip/gable roof has wide visible planes and limited ridge shadow, supporting an e… |
| gemini_multi | 6:12 | 1.1180 | 0.50 | `gemini_rejected_fallback` | all 3 Gemini shots failed |

## Solar API raw context

- whole_roof_area_sqft: **6117.8**
- ground_area_sqft: 5814.1
- weighted_pitch_deg: 18.08 (multiplier 1.0519)
- max_pitch_deg: 19.65, min_pitch_deg: 16.43
- roof_segment_count: 6
- imagery_quality: HIGH

## Footprint candidates (pick one for Path B; or use solar_whole for Path A)

| Source | Sqft | Detail |
|---|---:|---|
| solar_whole (slanted) | **6117.8** | Solar wholeRoofStats — IS the slanted roof area; segments=6, quality=HIGH |
| solar_ground (projected) | 5814.1 | Solar ground footprint estimate |
| ms | 5934.1 | MS PC closest polygon, distance=0.0 m, total_polys=99 |
| osm | 5861.2 | OSM closest polygon, distance=0.0 m, total_polys=148 |

## Street View context

- not available (None)
