import { useEffect, useRef, useState } from 'react';

const formatDisplayValue = (value, format) => {
  if (format === 'decimal') {
    return value.toFixed(1);
  }

  if (format === 'currency') {
    return Math.round(value).toLocaleString();
  }

  return Math.round(value).toLocaleString();
};

export default function MetricCard({ value, format, label, sub, accent = false }) {
  const [displayValue, setDisplayValue] = useState(0);
  const frameRef = useRef(null);
  const isNumericValue = typeof value === 'number';

  useEffect(() => {
    window.cancelAnimationFrame(frameRef.current);

    if (!isNumericValue) {
      return undefined;
    }

    const startTime = performance.now();

    const animateValue = (now) => {
      const progress = Math.min((now - startTime) / 800, 1);
      const easedProgress = 1 - Math.pow(1 - progress, 3);

      setDisplayValue(easedProgress * value);

      if (progress < 1) {
        frameRef.current = window.requestAnimationFrame(animateValue);
      } else {
        setDisplayValue(value);
      }
    };

    frameRef.current = window.requestAnimationFrame(animateValue);

    return () => window.cancelAnimationFrame(frameRef.current);
  }, [value, isNumericValue]);

  const renderedValue = isNumericValue ? formatDisplayValue(displayValue, format) : value;

  return (
    <article className="metric-card">
      <p className={accent ? 'metric-value metric-value-accent' : 'metric-value'}>
        {renderedValue}
      </p>
      <p className="metric-label">{label}</p>
      <p className="metric-sub">{sub}</p>
    </article>
  );
}
