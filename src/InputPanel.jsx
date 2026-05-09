import { MapPin, ScanLine, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

const pitchOptions = ['4:12', '6:12', '8:12', '10:12', '12:12'];

export default function InputPanel({ results, loading, onAnalyze }) {
  const [address, setAddress] = useState('');
  const [pitch, setPitch] = useState('6:12');
  const [displayedText, setDisplayedText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const googleApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

    if (!googleApiKey || !inputRef.current) {
      return undefined;
    }

    let autocomplete;
    let listener;
    const scriptId = 'google-maps-places-sdk';

    const initializeAutocomplete = () => {
      if (!window.google?.maps?.places || !inputRef.current) {
        return;
      }

      autocomplete = new window.google.maps.places.Autocomplete(inputRef.current, {
        types: ['address'],
        componentRestrictions: { country: 'us' },
      });

      listener = autocomplete.addListener('place_changed', () => {
        const place = autocomplete.getPlace();

        if (place.formatted_address) {
          setAddress(place.formatted_address);
        }
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

  useEffect(() => {
    if (!results) {
      setDisplayedText('');
      setIsTyping(false);
      return undefined;
    }

    const fullText = `${results.pixelArea.toLocaleString()} px² × ${results.gsd} ft²/px
× ${results.pitchMultiplier} pitch (${results.pitch})
= ${results.sqft.toLocaleString()} sqft`;
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
              ref={inputRef}
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
              {displayedText}
              {isTyping ? <span className="typewriter-cursor">|</span> : null}
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
