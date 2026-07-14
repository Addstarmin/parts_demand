const fmt = (value) => Number(value || 0).toLocaleString();

function ProductBomTable({ components, onSelectPart }) {
  if (!components?.length) {
    return <div className="empty-state">構成部品データがありません。</div>;
  }
  return (
    <div className="content-card">
      <div className="section-header">
        <div>
          <p className="section-label">BOM</p>
          <h2>構成部品別需要（選択製品由来）</h2>
        </div>
        <span className="badge">BOM展開</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>部品ID</th>
            <th>部品名</th>
            <th>1製品当たり</th>
            <th>部品需要</th>
            <th>生産推奨量</th>
            <th>発注推奨量</th>
            <th>出荷推奨量</th>
            <th>4週間合計</th>
            <th>現在庫</th>
            <th>動的安全在庫</th>
            <th>不足見込み</th>
            <th>LT</th>
          </tr>
        </thead>
        <tbody>
          {components.map((item) => (
            <tr key={item.parts_id} className="clickable-row" onClick={() => onSelectPart(item)}>
              <td>{item.parts_id}</td>
              <td>{item.parts_name}</td>
              <td>{fmt(item.quantity_per_product)}個</td>
              <td>{fmt(item.parts_demand ?? item.next_week_required)}個</td>
              <td>{fmt(item.recommended_production)}個</td>
              <td>{fmt(item.recommended_order)}個</td>
              <td>{fmt(item.recommended_shipping)}個</td>
              <td>{fmt(item.four_week_required)}個</td>
              <td>{fmt(item.current_stock)}個</td>
              <td>{fmt(item.dynamic_safety_stock)}個</td>
              <td>{fmt(item.shortage)}個</td>
              <td>{item.lead_time_weeks}週</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">共通部品は、ここでは選択製品由来の必要数のみを表示しています。</p>
    </div>
  );
}

export default ProductBomTable;
