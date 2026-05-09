import { Layers, ChevronDown, ChevronUp, FileText } from 'lucide-react';
import { useState } from 'react';

const truncate = (s, n = 90) => (!s ? '' : s.length > n ? s.slice(0, n - 1) + '…' : s);

function ConfBar({ value }) {
  const pct = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
  return (
    <div className="conf-bar" title={`Confidence ${pct}%`}>
      <div className="conf-bar-fill" style={{ width: `${pct}%` }} />
      <span className="conf-bar-label">{pct}%</span>
    </div>
  );
}

export default function FirstPassPanel({ firstPass, slug }) {
  const [open, setOpen] = useState(false);
  const [dossierOpen, setDossierOpen] = useState(false);
  const [dossierText, setDossierText] = useState('');
  const [dossierLoading, setDossierLoading] = useState(false);

  if (!firstPass) return null;
  const candidates = firstPass.candidates || [];
  const footprints = firstPass.footprints || {};

  const fpRows = [];
  if (footprints.aerial) fpRows.push({ key: 'aerial', ...footprints.aerial });
  if (footprints.publicMs)
    fpRows.push({ key: 'publicMs', label: footprints.publicMs.label || 'Public footprints (MS)', ...footprints.publicMs });
  if (footprints.publicOsm)
    fpRows.push({ key: 'publicOsm', label: footprints.publicOsm.label || 'Public footprints (OSM)', ...footprints.publicOsm });

  const handleViewDossier = async () => {
    if (!slug) return;
    setDossierOpen(true);
    if (dossierText) return;
    setDossierLoading(true);
    try {
      const r = await fetch(`/api/image/${slug}/dossier.md`);
      const t = await r.text();
      setDossierText(t);
    } catch (e) {
      setDossierText(`Failed to load dossier: ${e.message}`);
    } finally {
      setDossierLoading(false);
    }
  };

  return (
    <section className="firstpass-panel">
      <header
        className="firstpass-header"
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ' ? setOpen((o) => !o) : null)}
      >
        <div className="firstpass-title">
          <Layers size={16} strokeWidth={1.8} aria-hidden="true" />
          <span>First-pass evidence</span>
          <span className="firstpass-count">{candidates.length} candidates</span>
        </div>
        {open ? (
          <ChevronUp size={16} aria-hidden="true" />
        ) : (
          <ChevronDown size={16} aria-hidden="true" />
        )}
      </header>

      {open ? (
        <div className="firstpass-body">
          <h4 className="firstpass-subhead">Pitch candidates</h4>
          <div className="firstpass-table">
            <div className="firstpass-row firstpass-row-head">
              <div>Method</div>
              <div>Pitch</div>
              <div>Confidence</div>
              <div>Reasoning</div>
            </div>
            {candidates.map((c, i) => (
              <div className="firstpass-row" key={i}>
                <div className="firstpass-cell-method">{c.label}</div>
                <div className="firstpass-cell-pitch">{c.pitch || '—'}</div>
                <div>
                  <ConfBar value={c.confidence} />
                </div>
                <div className="firstpass-cell-reasoning" title={c.reasoning}>
                  {truncate(c.reasoning, 120)}
                </div>
              </div>
            ))}
          </div>

          {fpRows.length > 0 ? (
            <>
              <h4 className="firstpass-subhead">Footprint candidates</h4>
              <div className="firstpass-table">
                <div className="firstpass-row firstpass-row-head firstpass-row-fp">
                  <div>Source</div>
                  <div>Area (sqft)</div>
                  <div>Distance / segments</div>
                </div>
                {fpRows.map((fp) => (
                  <div className="firstpass-row firstpass-row-fp" key={fp.key}>
                    <div className="firstpass-cell-method">{fp.label || fp.key}</div>
                    <div>{fp.areaSqft != null ? fp.areaSqft : '—'}</div>
                    <div>
                      {fp.distanceM != null
                        ? `${fp.distanceM} m`
                        : fp.segments != null
                        ? `${fp.segments} segments`
                        : '—'}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : null}

          {slug ? (
            <button className="firstpass-dossier-btn" type="button" onClick={handleViewDossier}>
              <FileText size={14} strokeWidth={1.8} aria-hidden="true" />
              View raw dossier
            </button>
          ) : null}
        </div>
      ) : null}

      {dossierOpen ? (
        <div
          className="dossier-modal-backdrop"
          role="dialog"
          aria-modal="true"
          onClick={() => setDossierOpen(false)}
        >
          <div className="dossier-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dossier-modal-head">
              <span>Evidence dossier</span>
              <button type="button" onClick={() => setDossierOpen(false)}>
                Close
              </button>
            </div>
            <pre className="dossier-modal-body">
              {dossierLoading ? 'Loading…' : dossierText}
            </pre>
          </div>
        </div>
      ) : null}
    </section>
  );
}
