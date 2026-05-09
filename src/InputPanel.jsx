import { MapPin, ScanLine } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

const formatNumber = (n) => new Intl.NumberFormat('en-US').format(Math.round(n));

export default function InputPanel({ results, loading, error, onAnalyze }) {
  const [address, setAddress] = useState('');
  const [displayedText, setDisplayedText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const inputRef = useRef(null);

  // Google Places autocomplete (preserved from intern's shell)
  useEffect(() => {
    const googleApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
    if (!googleApiKey || !inputRef.current) return undefined;

    let autocomplete;
    let listener;
    const scriptId = 'google-maps-places-sdk';

    const initializeAutocomplete = () => {
      if (!window.google?.maps?.places || !inputRef.current) return;
      autocomplete = new window.google.maps.places.Autocomplete(inputRef.current, {
        types: ['address'],
        componentRestrictions: { country: 'us' },
      });
      listener = autocomplete.addListener('place_changed', () => {
        const place = autocomplete.getPlace();
        if (place.formatted_address) setAddress(place.formatted_address);
      });
    };

    if (window.google?.maps?.places) {
      initializeAutocomplete();
    } else {
      let script = document.getElementById(scriptId);
      if (!script) {
        script = document.createElement('script');
        script.id = scriptId;
        script.async = true;
        script.defer = true;
        script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(
          googleApiKey,
        )}&libraries=places`;
        document.head.appendChild(script);
      }
      script.addEventListener('load', initializeAutocomplete);
    }

    return () => {
      listener?.remove();
      document.getElementById(scriptId)?.removeEventListener('load', initializeAutocomplete);
    };
  }, []);

  // Math typewriter — uses REAL synthesizer numbers when results land.
  useEffect(() => {
    if (!results || !results.sqft) {
      setDisplayedText('');
      setIsTyping(false);
      return undefined;
    }

    const fp = results.footprintSqft != null ? formatNumber(results.footprintSqft) : '—';
    const mult = results.pitchMultiplier != null ? results.pitchMultiplier.toFixed(3) : '—';
    const pitchLabel = results.pitch || '—';
    const finalSqft = formatNumber(results.sqft);

    const fullText = `${fp} ft² footprint × ${mult} (${pitchLabel} pitch)
= ${finalSqft} sqft total`;
    let nextIndex = 0;
    setDisplayedText('');
    setIsTyping(true);

    const intervalId = window.setInterval(() => {
      nextIndex += 1;
      setDisplayedText(fullText.slice(0, nextIndex));
      if (nextIndex >= fullText.length) {
        window.clearInterval(intervalId);
        setIsTyping(false);
      }
    }, 18);

    return () => window.clearInterval(intervalId);
  }, [results]);

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!address.trim()) return;
    onAnalyze(address.trim());
  };

  const confidencePct =
    results && results.confidence != null ? Math.round(results.confidence * 100) : null;

  return (
    <aside className="input-panel">
      <form className="input-stack" onSubmit={handleSubmit}>
        <section className="panel-section">
          <p className="section-label">Property address</p>
          <label className="address-field">
            <MapPin size={15} strokeWidth={1.8} aria-hidden="true" />
            <input
              ref={inputRef}
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              placeholder="Enter property address…"
              type="text"
              autoComplete="off"
            />
          </label>
        </section>

        <div className="divider" />

        <section className="panel-section">
          <p className="section-label">Roof pitch</p>
          <div className="pitch-row">
            <span>Auto-detected by PitchPoint</span>
            <span className="pitch-readout">{results?.pitch || '—'}</span>
          </div>
          {confidencePct !== null ? (
            <p className="confidence-line">
              <span aria-hidden="true" />
              Confidence {confidencePct}% · {results?.synthesizer?.pathLabel || 'synth pending'}
            </p>
          ) : null}
        </section>

        <div className="divider" />

        <section className="panel-section">
          <p className="section-label">Math</p>
          {results ? (
            <div className="math-pill" aria-live="polite">
              {displayedText}
              {isTyping ? <span className="typewriter-cursor">|</span> : null}
            </div>
          ) : (
            <p className="math-placeholder">Footprint × pitch math appears here after analysis.</p>
          )}
        </section>

        {error ? (
          <div className="panel-error" role="alert">
            {error}
          </div>
        ) : null}

        <div className="panel-actions">
          <div className="step-dots" aria-label="Analysis progress">
            {[0, 1, 2, 3].map((step) => (
              <span
                key={step}
                className={
                  loading
                    ? `step-dot ${step < 2 ? 'step-dot-active' : ''}`
                    : results
                    ? 'step-dot step-dot-active'
                    : 'step-dot'
                }
                aria-hidden="true"
              />
            ))}
          </div>

          <button className="primary-button" type="submit" disabled={loading || !address.trim()}>
            <ScanLine size={14} strokeWidth={2} aria-hidden="true" />
            {loading ? 'Analyzing…' : 'Analyze roof'}
          </button>
        </div>
      </form>
    </aside>
  );
}
