import { useEffect, useRef, useState } from 'react';
import Navbar from './Navbar.jsx';
import InputPanel from './InputPanel.jsx';
import ResultsPanel from './ResultsPanel.jsx';
import Toast from './Toast.jsx';

export default function App() {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [toastVisible, setToastVisible] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(null);
  const toastTimerRef = useRef(null);
  const startTimeRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    return () => {
      window.clearTimeout(toastTimerRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  const handleAnalyze = async (address) => {
    if (!address) return;

    window.clearTimeout(toastTimerRef.current);
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();
    startTimeRef.current = Date.now();
    setResults(null);
    setError(null);
    setLoading(true);
    setToastVisible(false);

    try {
      const url = `/api/analyze?address=${encodeURIComponent(address)}`;
      const resp = await fetch(url, { signal: abortRef.current.signal });
      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
      }
      const data = await resp.json();
      setResults(data);
      setElapsedTime(((Date.now() - startTimeRef.current) / 1000).toFixed(1));
      setToastVisible(true);
      toastTimerRef.current = window.setTimeout(() => setToastVisible(false), 4000);
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error(e);
      setError(e.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <Navbar />
      <main className="app-layout">
        <InputPanel
          results={results}
          loading={loading}
          error={error}
          onAnalyze={handleAnalyze}
        />
        <ResultsPanel results={results} loading={loading} />
      </main>
      <Toast visible={toastVisible} elapsed={elapsedTime} />
    </div>
  );
}
