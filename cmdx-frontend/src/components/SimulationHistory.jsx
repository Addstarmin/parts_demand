function SimulationHistory({ history }) {
  if (!history?.length) return <div className="empty-state">シミュレーション履歴はまだありません。</div>;
  return (
    <div className="content-card">
      <div className="section-header">
        <div>
          <p className="section-label">History</p>
          <h2>直近の内示シミュレーション</h2>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>実行日時</th>
            <th>工場</th>
            <th>メーカー</th>
            <th>調整率</th>
            <th>通常</th>
            <th>調整後</th>
            <th>差分</th>
            <th>処理時間</th>
          </tr>
        </thead>
        <tbody>
          {history.slice(0, 5).map((item) => (
            <tr key={item.simulation_id}>
              <td>{item.executed_at}</td>
              <td>{item.factory_id}</td>
              <td>{item.manufacturer_id}</td>
              <td>{item.adjustment_rate}%</td>
              <td>{Number(item.normal_total).toLocaleString()}個</td>
              <td>{Number(item.adjusted_total).toLocaleString()}個</td>
              <td>{Number(item.difference).toLocaleString()}個</td>
              <td>{item.calculation_time_ms}ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default SimulationHistory;
