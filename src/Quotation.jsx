const formatCurrency = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);

const lineItems = [
  { key: 'tearoff', name: 'Tear-off & disposal', low: 75, high: 125 },
  { key: 'materials', name: 'Materials', low: 150, high: 250 },
  { key: 'labor', name: 'Labor & installation', low: 100, high: 175 },
  { key: 'permits', name: 'Permits & overhead', low: 25, high: 25 },
];

export default function Quotation({ results }) {
  const squares = results.squaresWithWaste ?? results.squares ?? 0;

  const rows = lineItems.map((item) => ({
    ...item,
    lowAmount: Math.round(item.low * squares),
    highAmount: Math.round(item.high * squares),
  }));

  const totalLow = rows.reduce((sum, r) => sum + r.lowAmount, 0);
  const totalHigh = rows.reduce((sum, r) => sum + r.highAmount, 0);

  return (
    <article className="quotation-card">
      <div className="quotation-header">
        <h2>Quotation</h2>
        <span>{squares.toFixed(1)} sq · +15% waste</span>
      </div>
      <div className="quotation-list">
        {rows.map((item) => {
          const rate =
            item.low === item.high
              ? `$${item.low}/sq`
              : `$${item.low}–$${item.high}/sq`;
          const amount =
            item.lowAmount === item.highAmount
              ? formatCurrency(item.lowAmount)
              : `${formatCurrency(item.lowAmount)} – ${formatCurrency(item.highAmount)}`;
          return (
            <div className="quotation-row" key={item.key}>
              <div className="quotation-name">{item.name}</div>
              <div className="quotation-rate">{rate}</div>
              <div className="quotation-amount">{amount}</div>
            </div>
          );
        })}
      </div>
      <div className="quotation-total">
        <span>Total</span>
        <strong>
          {formatCurrency(totalLow)} – {formatCurrency(totalHigh)}
        </strong>
      </div>
    </article>
  );
}
