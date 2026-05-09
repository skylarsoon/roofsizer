import { Brain, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

export default function SynthesizerPanel({ synthesizer, manualReviewNeeded }) {
  const [open, setOpen] = useState(true);
  if (!synthesizer) return null;

  const {
    pathLabel,
    footprintSource,
    pitchSource,
    reasoning,
  } = synthesizer;

  return (
    <section className="synth-panel">
      <header
        className="synth-panel-header"
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ' ? setOpen((o) => !o) : null)}
      >
        <div className="synth-panel-title">
          <Brain size={16} strokeWidth={1.8} aria-hidden="true" />
          <span>Synthesizer decision</span>
          {pathLabel ? <span className="synth-path-badge">{pathLabel}</span> : null}
        </div>
        {open ? (
          <ChevronUp size={16} aria-hidden="true" />
        ) : (
          <ChevronDown size={16} aria-hidden="true" />
        )}
      </header>

      {open ? (
        <div className="synth-panel-body">
          {manualReviewNeeded ? (
            <div className="synth-warning" role="alert">
              <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
              <span>Low confidence — manual review recommended.</span>
            </div>
          ) : null}

          <div className="synth-grid">
            <div>
              <p className="synth-grid-label">Footprint source</p>
              <p className="synth-grid-value">{footprintSource || '—'}</p>
            </div>
            <div>
              <p className="synth-grid-label">Pitch source</p>
              <p className="synth-grid-value">{pitchSource || '—'}</p>
            </div>
          </div>

          {reasoning ? (
            <blockquote className="synth-reasoning">
              <span aria-hidden="true">“</span>
              {reasoning}
              <span aria-hidden="true">”</span>
            </blockquote>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
