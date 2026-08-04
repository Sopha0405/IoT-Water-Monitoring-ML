const METRICS = [
  { key: 'precision', label: 'Precision' },
  { key: 'recall', label: 'Recall' },
  { key: 'f1', label: 'F1' },
  { key: 'fpr', label: 'FPR' },
];

function toPercent(value) {
  const num = Number(value || 0);
  return Math.max(0, Math.min(100, num <= 1 ? num * 100 : num));
}

function formatPercent(value) {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '-';
}

export function ModelComparisonChart({ active, candidate }) {
  const hasData = active?.exists || candidate?.exists;

  if (!hasData) {
    return <div className="compare-empty">Aun no hay un modelo activo ni candidato para comparar.</div>;
  }

  return (
    <div className="compare-chart-wrap">
      <div className="compare-chart-groups">
        {METRICS.map((metric) => {
          const activeValue = active?.metrics?.[metric.key];
          const candidateValue = candidate?.metrics?.[metric.key];
          return (
            <div className="compare-group" key={metric.key}>
              <div className="compare-group-label">
                <strong>{metric.label}</strong>
              </div>
              <div className="compare-bars">
                <div className="compare-bar-row">
                  <span>Activo</span>
                  <div className="compare-bar-track">
                    <div
                      className="compare-bar-fill active-fill"
                      style={{ width: `${toPercent(activeValue)}%` }}
                    />
                  </div>
                  <span className="compare-bar-value">{formatPercent(activeValue)}</span>
                </div>
                <div className="compare-bar-row">
                  <span>Candidato</span>
                  <div className="compare-bar-track">
                    <div
                      className="compare-bar-fill candidate-fill"
                      style={{ width: `${toPercent(candidateValue)}%` }}
                    />
                  </div>
                  <span className="compare-bar-value">{formatPercent(candidateValue)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
