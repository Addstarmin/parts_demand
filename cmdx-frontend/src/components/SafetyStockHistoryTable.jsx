function SafetyStockHistoryTable({ history }) {
  if (!history?.length) return <div className="empty-state">安全在庫変更履歴はまだありません。</div>;
  return (
    <div className="content-card">
      <div className="section-header">
        <div>
          <p className="section-label">History</p>
          <h2>安全在庫変更履歴</h2>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>実行日時</th>
            <th>工場</th>
            <th>部品</th>
            <th>旧値</th>
            <th>新値</th>
            <th>差</th>
            <th>RMSE</th>
            <th>LT</th>
            <th>実行種別</th>
          </tr>
        </thead>
        <tbody>
          {history.slice(0, 20).map((item) => (
            <tr key={item.history_id}>
              <td>{item.executed_at}</td>
              <td>{item.factory_id}</td>
              <td>{item.parts_id}</td>
              <td>{Number(item.old_safety_stock).toLocaleString()}個</td>
              <td>{Number(item.new_safety_stock).toLocaleString()}個</td>
              <td>{Number(item.difference).toLocaleString()}個</td>
              <td>{Number(item.rmse).toLocaleString()}</td>
              <td>{item.lead_time_days}日</td>
              <td>{item.execution_type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default SafetyStockHistoryTable;
