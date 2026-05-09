# Roof pitch evidence dossier

**Address:** 3561 E 102nd Ct, Thornton, CO 80229
**Geocoded:** 39.88116, -104.94538

## Candidate pitch estimates

| Method | Rise/12 | Multiplier | Confidence | Source | Reasoning |
|---|---:|---:|---:|---|---|
| regional | 7:12 | 1.1577 | 0.65 | `regional_default` |  |
| streetview | 7:12 | 1.1577 | 0.72 | `streetview` | The front gable slope is clearly visible and appears moderately steep around 30 degrees. |
| gpt_multi | 6:12 | 1.1180 | 0.57 | `llm_multi` | A complex hip/gable roof with moderate shadows and broad slope widths indicates a typical residential pitch.; A complex intersecting-gable roof with moderate shadows and moderate slope widths suggests a typical-to-slight… |
| gemini_multi | 6:12 | 1.1180 | 0.50 | `gemini_rejected_fallback` | all 3 Gemini shots failed |

## Solar API raw context

- whole_roof_area_sqft: **2080.8**
- ground_area_sqft: 1681.4
- weighted_pitch_deg: 36.01 (multiplier 1.2362)
- max_pitch_deg: 41.54, min_pitch_deg: 29.83
- roof_segment_count: 9
- imagery_quality: HIGH

## Footprint candidates (pick one for Path B; or use solar_whole for Path A)

| Source | Sqft | Detail |
|---|---:|---|
| solar_whole (slanted) | **2080.8** | Solar wholeRoofStats — IS the slanted roof area; segments=9, quality=HIGH |
| solar_ground (projected) | 1681.4 | Solar ground footprint estimate |
| ms | 1688.4 | MS PC closest polygon, distance=0.0 m, total_polys=61 |
| osm | — | no OSM polygons in bbox |

## Street View context

- not available (None)
