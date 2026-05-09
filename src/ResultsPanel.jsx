import EstimateBar from './EstimateBar.jsx';
import ImagePreview from './ImagePreview.jsx';
import LineItems from './LineItems.jsx';
import MetricCard from './MetricCard.jsx';

export default function ResultsPanel({ results, loading }) {
  return (
    <section className="results-panel">
      <ImagePreview results={results} loading={loading} />

      {results ? (
        <div className="results-content results-content-visible">
          <div className="metric-row">
            <MetricCard
              value={results.sqft}
              format="number"
              label="Total sqft"
              sub="Roof area"
            />
            <MetricCard
              value={results.squares}
              format="decimal"
              label="Squares"
              sub={`+15% waste = ${results.squaresWithWaste.toFixed(1)}`}
            />
            <MetricCard
              value={results.pitch}
              format="number"
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
