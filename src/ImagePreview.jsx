import { Building2 } from 'lucide-react';
import { useEffect, useState } from 'react';

const formatNumber = (value) => new Intl.NumberFormat('en-US').format(value);

export default function ImagePreview({ results, loading }) {
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    if (!results) {
      setAnimate(false);
      return;
    }

    setAnimate(false);
    const frameId = window.requestAnimationFrame(() => setAnimate(true));

    return () => window.cancelAnimationFrame(frameId);
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

  return (
    <div className="image-preview image-preview-results">
      <svg className="roof-overlay" viewBox="0 0 400 240" aria-label="Detected roof polygon">
        <polygon
          className={`roof-polygon ${animate ? 'draw' : ''}`}
          points="200,30 340,100 320,190 80,190 60,100"
          fill="rgba(99,153,34,0.15)"
          stroke="#639922"
          strokeWidth="2.5"
          strokeDasharray="640"
          strokeDashoffset="640"
        />
        <line
          className={`ridge-line ${animate ? 'draw' : ''}`}
          x1="128"
          y1="102"
          x2="286"
          y2="102"
          stroke="#E24B4A"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray="160"
          strokeDashoffset="160"
        />
        <g className={`roof-label ${animate ? 'show' : ''}`}>
          <rect x="164" y="55" width="72" height="23" rx="11.5" />
          <text x="200" y="70">
            {formatNumber(results.sqft)} sqft
          </text>
        </g>
      </svg>
    </div>
  );
}
