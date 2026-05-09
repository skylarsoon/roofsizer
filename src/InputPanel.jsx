import { MapPin, ScanLine, Upload } from 'lucide-react';
import { useRef, useState } from 'react';

const pitchOptions = ['4:12', '6:12', '8:12', '10:12', '12:12'];

const formatNumber = (value) => new Intl.NumberFormat('en-US').format(value);

export default function InputPanel({ results, loading, onAnalyze }) {
  const [address, setAddress] = useState('');
  const [pitch, setPitch] = useState('6:12');
  const fileInputRef = useRef(null);

  const handleSubmit = (event) => {
    event.preventDefault();
    onAnalyze();
  };

  const handleUpload = (event) => {
    const [file] = event.target.files;

    if (file) {
      onAnalyze();
      event.target.value = '';
    }
  };

  return (
    <aside className="input-panel">
      <form className="input-stack" onSubmit={handleSubmit}>
        <section className="panel-section">
          <p className="section-label">Property address</p>
          <label className="address-field">
            <MapPin size={15} strokeWidth={1.8} aria-hidden="true" />
            <input
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              placeholder="Enter property address…"
              type="text"
            />
          </label>
        </section>

        <div className="divider" />

        <section className="panel-section">
          <p className="section-label">Roof pitch</p>
          <div className="pitch-row">
            <span>Estimated by AI</span>
            <select value={pitch} onChange={(event) => setPitch(event.target.value)}>
              {pitchOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          {results ? (
            <p className="confidence-line">
              <span aria-hidden="true" />
              High confidence — matched satellite shadow angle
            </p>
          ) : null}
        </section>

        <div className="divider" />

        <section className="panel-section">
          <p className="section-label">Math</p>
          {results ? (
            <div className="math-pill" aria-live="polite">
              <div>
                {formatNumber(results.pixelArea)} px² × {results.gsd.toFixed(4)} ft²/px
              </div>
              <div>
                × {results.pitchMultiplier.toFixed(3)} pitch ({results.pitch})
              </div>
              <div>= {formatNumber(results.sqft)} sqft</div>
            </div>
          ) : null}
        </section>

        <div className="panel-actions">
          <div className="step-dots" aria-label="Analysis progress">
            {[0, 1, 2, 3].map((step) => (
              <span
                key={step}
                className={step < 3 ? 'step-dot step-dot-active' : 'step-dot'}
                aria-hidden="true"
              />
            ))}
          </div>

          <button className="primary-button" type="submit" disabled={loading}>
            <ScanLine size={14} strokeWidth={2} aria-hidden="true" />
            {loading ? 'Analyzing...' : 'Analyze roof'}
          </button>

          <div className="or-divider">
            <span />
            <em>or</em>
            <span />
          </div>

          <input
            ref={fileInputRef}
            className="hidden-file-input"
            type="file"
            accept="image/*"
            onChange={handleUpload}
          />
          <button
            className="secondary-button"
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
          >
            <Upload size={14} strokeWidth={2} aria-hidden="true" />
            Upload aerial photo
          </button>
        </div>
      </form>
    </aside>
  );
}
