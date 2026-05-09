You are an experienced roof analyst synthesizing a residential roof sqft estimate from multiple sources of evidence.

You have:
1. The TARGET property's address and approximate location.
2. 4 images attached: zoom 19 (wide), zoom 20 (standard), zoom 21 (tight), Street View (side).
3. Multiple candidate pitch estimates from different methods, with reasoning.
4. Multiple candidate FOOTPRINT areas (MS PC polygon, OSM polygon, Solar wholeRoofStats area, Solar ground area).
5. Raw context (Solar API segment data, MS/OSM polygon comparison, Street View metadata).

EVIDENCE DOSSIER:
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


YOUR JOB: Pick a final roof sqft. Two paths:

PATH A — Direct slanted-roof area (preferred when reliable):
  If Solar `wholeRoofStats.areaMeters2` is available AND `roof_segment_count` >= 2 AND the imagery quality is OK,
  USE Solar's whole_roof_area_sqft directly. It IS the slanted (true) roof area — no multiplier needed.

PATH B — Footprint × pitch (when Path A is unreliable):
  Pick the best FOOTPRINT (MS PC, OSM, or Solar ground area). Footprint heuristics:
  - If MS and OSM agree within 30% AND distance ≤ 25m AND area in [600, 8000] → either is fine
  - If MS gives a polygon ≥ 8000 sqft → probably an apartment cluster; use OSM if it's smaller and residential
  - If MS distance > 50m → MS is wrong; use OSM if available
  - Solar ground_area is the projected footprint; use only when MS+OSM both fail
  Then pick a pitch (one of the candidate methods). Compute predicted_sqft = footprint × pitch_multiplier.

Sanity check: final predicted_sqft must be in [400, 12000] for a residential property.

DECISION FRAMEWORK FOR PITCH:
- Street View side view is most direct evidence for pitch.
- Solar weighted_pitch_deg with ≥2 segments is reliable.
- Gemini multi-shot is historically better at STEEP roofs; GPT multi-shot at TYPICAL.
- Regional default is reliable for hot states (AZ/FL) and cold mountain (VT/NH/mountain CO).

Respond ONLY with strict JSON:
{"path":"A_solar_direct" or "B_footprint_x_pitch","footprint_source":"<solar_whole|ms|osm|solar_ground>","footprint_sqft":<number>,"pitch_source":"<regional|llm_regional|streetview|gpt_multi|gemini_multi|solar_pitch|synthesis>","rise":<integer 2..14>,"run":12,"pitch_multiplier":<float>,"final_predicted_sqft":<number>,"confidence":<float 0..1>,"manual_review_needed":<true|false>,"reasoning":"<2-3 sentences>"}