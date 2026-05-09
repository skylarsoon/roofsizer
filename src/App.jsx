import { useRef, useState } from 'react';
import Navbar from './Navbar.jsx';
import InputPanel from './InputPanel.jsx';
import ResultsPanel from './ResultsPanel.jsx';

const mockResults = {
  sqft: 2443,
  squares: 24.4,
  squaresWithWaste: 28.1,
  pitch: '6:12',
  pitchMultiplier: 1.118,
  pixelArea: 1847,
  gsd: 0.0024,
  lineItems: {
    eaves: 187,
    rakes: 101,
    ridge: 26,
    hips: 101,
    valleys: 40,
  },
  estimateLow: 8200,
  estimateHigh: 13400,
};

export default function App() {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);

  const handleAnalyze = () => {
    window.clearTimeout(timerRef.current);
    setResults(null);
    setLoading(true);

    timerRef.current = window.setTimeout(() => {
      setResults(mockResults);
      setLoading(false);
    }, 2500);
  };

  return (
    <div className="app-shell">
      <Navbar />
      <main className="app-layout">
        <InputPanel results={results} loading={loading} onAnalyze={handleAnalyze} />
        <ResultsPanel results={results} loading={loading} />
      </main>
    </div>
  );
}
