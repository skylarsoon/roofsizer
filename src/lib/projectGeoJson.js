// Project lat/lng from a GeoJSON Polygon onto SVG pixel coordinates for an
// orthorectified satellite image (Google Static Maps zoom 20, scale 2 by default).
//
// The image is centered on (centerLat, centerLng). We use a local Mercator
// approximation valid over the small bbox of one residential property.
//
// Reference: same math as src/data_sources/sam_mask.py:_pixel_to_lat_lng
// (we invert it: lat/lng → pixel).

const SQRT2 = Math.sqrt(2);

// Meters per pixel at the given lat / zoom / scale (Google Web Mercator).
function metersPerPixel(centerLat, zoom = 20, scale = 2) {
  const latRad = (centerLat * Math.PI) / 180;
  return (156543.03392 * Math.cos(latRad)) / (Math.pow(2, zoom) * scale);
}

// Convert (lat, lng) → pixel (x, y) within the image of given width/height in pixels.
// Origin (0,0) is the TOP-LEFT of the image. y grows downward.
function latLngToPixel(lat, lng, opts) {
  const { centerLat, centerLng, width, height, zoom = 20, scale = 2 } = opts;
  const mpp = metersPerPixel(centerLat, zoom, scale);
  const dLat = lat - centerLat;
  const dLng = lng - centerLng;
  const dyMeters = -dLat * 111320.0; // image-y grows southward
  const dxMeters =
    dLng * 111320.0 * Math.max(0.01, Math.cos((centerLat * Math.PI) / 180));
  const x = width / 2 + dxMeters / mpp;
  const y = height / 2 + dyMeters / mpp;
  return [x, y];
}

// Walk a GeoJSON Polygon or MultiPolygon and return an array of polygon-rings,
// each ring being an array of [x, y] svg coords for the given image dimensions.
export function geoJsonToSvgRings(geojson, opts) {
  if (!geojson) return [];

  // GeoJSON can be a FeatureCollection, Feature, or raw geometry.
  const feature =
    geojson.type === 'FeatureCollection'
      ? geojson.features?.[0]
      : geojson.type === 'Feature'
      ? geojson
      : { geometry: geojson };
  const geom = feature?.geometry;
  if (!geom) return [];

  const polys =
    geom.type === 'Polygon'
      ? [geom.coordinates]
      : geom.type === 'MultiPolygon'
      ? geom.coordinates
      : [];

  const rings = [];
  polys.forEach((polyCoords) => {
    polyCoords.forEach((ring) => {
      const pts = ring
        .map(([lng, lat]) => latLngToPixel(lat, lng, opts))
        // Filter NaN / out-of-range
        .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
      if (pts.length >= 3) rings.push(pts);
    });
  });
  return rings;
}

// Convenience: rings → SVG points string, e.g. "x1,y1 x2,y2 ..."
export function ringsToSvgPolygons(rings) {
  return rings.map((ring) => ring.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' '));
}
