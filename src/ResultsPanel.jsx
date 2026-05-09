import EstimateBar from './EstimateBar.jsx';
import ImagePreview from './ImagePreview.jsx';
import LineItems from './LineItems.jsx';
import MetricCard from './MetricCard.jsx';

const formatNumber = (value) => new Intl.NumberFormat('en-US').format(value);

export default function ResultsPanel({ results, loading }) {
  return (
    <section className="results-panel">
      <ImagePreview results={results} loading={loading} />

      {results ? (
        <div className="results-content results-content-visible">
          <div className="metric-row">
            <MetricCard
              value={formatNumber(results.sqft)}
              label="Total sqft"
              sub="Roof area"
            />
            <MetricCard
              value={results.squares.toFixed(1)}
              label="Squares"
              sub={`+15% waste = ${results.squaresWithWaste.toFixed(1)}`}
            />
            <MetricCard
              value={results.pitch}
              label="Pitch"
              sub={`×${results.pitchMultiplier.toFixed(3)} multiplier`}
              accent
            />
          </div>

          <LineItems lineItems={results.lineItems} />
          <EstimateBar results={results} />
        </div>
      ) : null}
    </section>
  );
}
