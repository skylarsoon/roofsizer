import FirstPassPanel from './FirstPassPanel.jsx';
import ImagePreview from './ImagePreview.jsx';
import LineItems from './LineItems.jsx';
import MetricCard from './MetricCard.jsx';
import Quotation from './Quotation.jsx';
import SynthesizerPanel from './SynthesizerPanel.jsx';

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
              sub="PitchPoint roof area"
            />
            <MetricCard
              value={results.squares}
              format="decimal"
              label="Squares"
              sub={
                results.squaresWithWaste != null
                  ? `+15% waste = ${results.squaresWithWaste.toFixed(1)}`
                  : null
              }
            />
            <MetricCard
              value={results.pitch}
              format="number"
              label="Pitch"
              sub={
                results.pitchMultiplier != null
                  ? `×${results.pitchMultiplier.toFixed(3)} multiplier`
                  : null
              }
              accent
            />
          </div>

          <SynthesizerPanel
            synthesizer={results.synthesizer}
            manualReviewNeeded={results.manualReviewNeeded}
          />

          <FirstPassPanel firstPass={results.firstPass} slug={results.slug} />

          {results.lineItems ? <LineItems lineItems={results.lineItems} /> : null}
          <Quotation results={results} />
        </div>
      ) : null}
    </section>
  );
}
