import { Building2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { geoJsonToSvgRings } from './lib/projectGeoJson.js';

const formatNumber = (value) =>
  value === undefined || value === null
    ? ''
    : new Intl.NumberFormat('en-US').format(Math.round(value));

// The cached static-map PNG is 1280×1280 (size=640x640 × scale=2). The SVG
// overlay uses the same drawing coordinate space scaled to the on-screen size.
const IMG_WIDTH = 1280;
const IMG_HEIGHT = 1280;
const SVG_W = 400;
const SVG_H = 240;

export default function ImagePreview({ results, loading }) {
  const [animate, setAnimate] = useState(false);
  const [polygonRings, setPolygonRings] = useState([]);
  const [polyLoading, setPolyLoading] = useState(false);

  useEffect(() => {
    if (!results) {
      setAnimate(false);
      setPolygonRings([]);
      return;
    }
    setAnimate(false);
    const frameId = window.requestAnimationFrame(() => setAnimate(true));
    return () => window.cancelAnimationFrame(frameId);
  }, [results]);

  useEffect(() => {
    let cancelled = false;
    setPolygonRings([]);
    if (!results || !results.footprintGeoJsonUrl) return undefined;

    const center =
      (results.geocode && results.geocode.lat !== undefined ? results.geocode : null) ||
      (results.lat !== undefined ? { lat: results.lat, lng: results.lng } : null);
    if (!center) return undefined;

    setPolyLoading(true);
    fetch(results.footprintGeoJsonUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((gj) => {
        if (cancelled) return;
        const rings = geoJsonToSvgRings(gj, {
          centerLat: center.lat,
          centerLng: center.lng,
          width: IMG_WIDTH,
          height: IMG_HEIGHT,
          zoom: 20,
          scale: 2,
        });
        const scaled = rings.map((ring) =>
          ring.map(([x, y]) => [(x / IMG_WIDTH) * SVG_W, (y / IMG_HEIGHT) * SVG_H])
        );
        setPolygonRings(scaled);
      })
      .catch((err) => {
        if (!cancelled) {
          console.warn('polygon load failed:', err);
          setPolygonRings([]);
        }
      })
      .finally(() => {
        if (!cancelled) setPolyLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [results]);

  if (loading) {
    return <div className="image-preview image-preview-loading" aria-label="Loading satellite view" />;
  }

  if (!results) {
    return (
      <div className="image-preview image-preview-empty">
        <Building2 size={28} strokeWidth={1.6} aria-hidden="true" />
        <p>Satellite view loads here</p>
      </div>
    );
  }

  const fallbackRing = [
    [200, 30],
    [340, 100],
    [320, 190],
    [80, 190],
    [60, 100],
  ];
  const usingFallback = polygonRings.length === 0;
  const rings = usingFallback ? [fallbackRing] : polygonRings;

  return (
    <div className="image-preview image-preview-results">
      {results.satelliteImageUrl ? (
        <img
          src={results.satelliteImageUrl}
          alt="Satellite view of property"
          className="image-preview-photo"
        />
      ) : null}
      <svg
        className="roof-overlay"
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        preserveAspectRatio="xMidYMid meet"
        aria-label="Detected roof polygon"
      >
        {rings.map((ring, i) => (
          <polygon
            key={i}
            className={`roof-polygon ${animate ? 'draw' : ''}`}
            points={ring.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ')}
            fill="rgba(34,211,238,0.16)"
            stroke="#22d3ee"
            strokeWidth="2.5"
            strokeDasharray="800"
            strokeDashoffset="800"
          />
        ))}
        <g className={`roof-label ${animate ? 'show' : ''}`}>
          <rect x={SVG_W / 2 - 44} y={10} width={88} height={22} rx={11} />
          <text x={SVG_W / 2} y={26}>
            {formatNumber(results.sqft)} sqft
          </text>
        </g>
      </svg>
    </div>
  );
}
