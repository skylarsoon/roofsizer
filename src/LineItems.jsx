const itemMeta = [
  { key: 'eaves', name: 'Eave', color: '#639922' },
  { key: 'rakes', name: 'Rake', color: '#1D9E75' },
  { key: 'ridge', name: 'Ridge', color: '#E24B4A' },
  { key: 'hips', name: 'Hip', color: '#378ADD' },
  { key: 'valleys', name: 'Valley', color: '#BA7517' },
];

export default function LineItems({ lineItems }) {
  return (
    <article className="line-items-card">
      <div className="line-items-header">
        <h2>Line items</h2>
        <span>Linear feet</span>
      </div>
      <div className="line-items-list">
        {itemMeta.map((item) => (
          <div className="line-item-row" key={item.key}>
            <div className="line-item-name">
              <span style={{ '--item-color': item.color }} aria-hidden="true" />
              {item.name}
            </div>
            <strong>{lineItems[item.key]} ft</strong>
          </div>
        ))}
      </div>
    </article>
  );
}
