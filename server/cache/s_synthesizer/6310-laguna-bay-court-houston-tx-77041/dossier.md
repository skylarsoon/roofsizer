# Roof pitch evidence dossier

**Address:** 6310 Laguna Bay Court, Houston, TX 77041
**Geocoded:** 29.86032, -95.59040

## Candidate pitch estimates

| Method | Rise/12 | Multiplier | Confidence | Source | Reasoning |
|---|---:|---:|---:|---|---|
| regional | 5:12 | 1.0833 | 0.65 | `regional_default` |  |
| streetview | 6:12 | 1.1180 | 0.05 | `streetview_rejected` | No Street View imagery is available, so the roof cannot be assessed. |
| gpt_multi | 7:12 | 1.1577 | 0.62 | `llm_multi` | The complex hip-and-gable roof shows typical-to-slightly-steep pitch cues with moderate shadows and moderate slope widths.; A complex hip-and-gable roof with moderate shadows and average slope widths suggests a typical r… |
| gemini_multi | 6:12 | 1.1180 | 0.50 | `gemini_rejected_fallback` | all 3 Gemini shots failed |

## Solar API raw context

- whole_roof_area_sqft: **4186.2**
- ground_area_sqft: 3417.2
- weighted_pitch_deg: 35.21 (multiplier 1.224)
- max_pitch_deg: 41.49, min_pitch_deg: 29.63
- roof_segment_count: 20
- imagery_quality: HIGH

## Footprint candidates (pick one for Path B; or use solar_whole for Path A)

| Source | Sqft | Detail |
|---|---:|---|
| solar_whole (slanted) | **4186.2** | Solar wholeRoofStats — IS the slanted roof area; segments=20, quality=HIGH |
| solar_ground (projected) | 3417.2 | Solar ground footprint estimate |
| ms | 3679.0 | MS PC closest polygon, distance=0.0 m, total_polys=62 |
| osm | 2418.5 | OSM closest polygon, distance=0.0 m, total_polys=70 |

## Street View context

- not available (no_streetview_coverage)
