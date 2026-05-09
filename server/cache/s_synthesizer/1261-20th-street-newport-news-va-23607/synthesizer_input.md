You are an experienced roof analyst synthesizing a residential roof sqft estimate from multiple sources of evidence.

You have:
1. The TARGET property's address and approximate location.
2. 4 images attached: zoom 19 (wide), zoom 20 (standard), zoom 21 (tight), Street View (side).
3. Multiple candidate pitch estimates from different methods, with reasoning.
4. Multiple candidate FOOTPRINT areas (MS PC polygon, OSM polygon, Solar wholeRoofStats area, Solar ground area).
5. Raw context (Solar API segment data, MS/OSM polygon comparison, Street View metadata).

EVIDENCE DOSSIER:
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