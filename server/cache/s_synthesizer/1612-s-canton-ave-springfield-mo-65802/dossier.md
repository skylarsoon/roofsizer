# Roof pitch evidence dossier

**Address:** 1612 S Canton Ave, Springfield, MO 65802
**Geocoded:** 37.18609, -93.36959

## Candidate pitch estimates

| Method | Rise/12 | Multiplier | Confidence | Source | Reasoning |
|---|---:|---:|---:|---|---|
| regional | 6:12 | 1.1180 | 0.65 | `regional_default` |  |
| streetview | 5:12 | 1.0833 | 0.75 | `streetview` | The visible ranch-style hip roof has a moderate low-to-typical slope around the 5:12 range. |
| gpt_multi | 5:12 | 1.0833 | 0.66 | `llm_multi` | The compound hipped roof has broad slope projections and only moderate shadows, indicating a typical-low residential pitch around 5:12.; A complex hipped suburban roof with broad planes and limited ridge shadow suggests … |
| gemini_multi | 6:12 | 1.1180 | 0.50 | `gemini_rejected_fallback` | all 3 Gemini shots failed |

## Solar API raw context

- whole_roof_area_sqft: **2756.8**
- ground_area_sqft: 2363.0
- weighted_pitch_deg: 30.89 (multiplier 1.1653)
- max_pitch_deg: 38.11, min_pitch_deg: 22.26
- roof_segment_count: 10
- imagery_quality: HIGH

## Footprint candidates (pick one for Path B; or use solar_whole for Path A)

| Source | Sqft | Detail |
|---|---:|---|
| solar_whole (slanted) | **2756.8** | Solar wholeRoofStats — IS the slanted roof area; segments=10, quality=HIGH |
| solar_ground (projected) | 2363.0 | Solar ground footprint estimate |
| ms | 2290.5 | MS PC closest polygon, distance=0.0 m, total_polys=31 |
| osm | — | no OSM polygons in bbox |

## Street View context

- not available (None)
