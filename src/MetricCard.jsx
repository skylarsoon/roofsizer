export default function MetricCard({ value, label, sub, accent = false }) {
  return (
    <article className="metric-card">
      <p className={accent ? 'metric-value metric-value-accent' : 'metric-value'}>{value}</p>
      <p className="metric-label">{label}</p>
      <p className="metric-sub">{sub}</p>
    </article>
  );
}
