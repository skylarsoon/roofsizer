# Roof pitch evidence dossier

**Address:** 3820 E Rosebrier St, Springfield, MO 65809
**Geocoded:** 37.15969, -93.21595

## Candidate pitch estimates

| Method | Rise/12 | Multiplier | Confidence | Source | Reasoning |
|---|---:|---:|---:|---|---|
| regional | 6:12 | 1.1180 | 0.65 | `regional_default` |  |
| streetview | 5:12 | 1.0833 | 0.78 | `streetview` | The visible hip roof has a moderate low-to-typical slope around the low 20-degree range. |
| gpt_multi | 5:12 | 1.0833 | 0.56 | `llm_multi` | Complex hipped roof with limited shadowing and broad slope widths suggests a typical-to-slightly-shallow pitch.; A complex hipped roof with moderate shadows and medium slope widths suggests a typical-to-slightly-steep re… |
| gemini_multi | 6:12 | 1.1180 | 0.50 | `gemini_rejected_fallback` | all 3 Gemini shots failed |

## Solar API raw context

- whole_roof_area_sqft: **5566.1**
- ground_area_sqft: 4951.6
- weighted_pitch_deg: 27.04 (multiplier 1.1227)
- max_pitch_deg: 44.4, min_pitch_deg: 20.33
- roof_segment_count: 18
- imagery_quality: HIGH

## Footprint candidates (pick one for Path B; or use solar_whole for Path A)

| Source | Sqft | Detail |
|---|---:|---|
| solar_whole (slanted) | **5566.1** | Solar wholeRoofStats — IS the slanted roof area; segments=18, quality=HIGH |
| solar_ground (projected) | 4951.6 | Solar ground footprint estimate |
| ms | 4942.0 | MS PC closest polygon, distance=0.0 m, total_polys=37 |
| osm | — | no OSM polygons in bbox |

## Street View context

- not available (None)
