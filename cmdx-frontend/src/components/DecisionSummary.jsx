function DecisionSummary({ result }) {
  if (!result) return null;
  return (
    <div className={`decision-summary ${result.adjustment_rate < 0 ? "down" : result.adjustment_rate > 0 ? "up" : ""}`}>
      <div>
        <p className="section-label">Decision Summary</p>
        <h2>{result.direction}内示シミュレーション</h2>
        <p>{result.summary}</p>
      </div>
      <div className="summary-metrics">
        <strong>{Number(result.difference).toLocaleString()}個</strong>
        <span>4週間差分</span>
        <span>{result.calculation_time_ms}ms</span>
      </div>
    </div>
  );
}

export default DecisionSummary;
