import { FileText } from 'lucide-react';

const formatCurrency = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);

export default function EstimateBar({ results }) {
  return (
    <article className="estimate-bar">
      <div>
        <p className="estimate-label">Estimated total</p>
        <p className="estimate-value">
          {formatCurrency(results.estimateLow)} – {formatCurrency(results.estimateHigh)}
        </p>
        <p className="estimate-sub">Materials + labor · {results.squares.toFixed(1)} squares</p>
      </div>
      <button type="button" onClick={() => window.print()}>
        <FileText size={14} strokeWidth={2} aria-hidden="true" />
        Export PDF
      </button>
    </article>
  );
}
