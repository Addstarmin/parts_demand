function AlertPanel({ forecast }) {
  if (!forecast) return null;

  const isCritical = forecast.risk_level === "CRITICAL";
  const isWarning = forecast.risk_level === "WARNING";

  const alertClass = isCritical
    ? "alert-panel critical"
    : isWarning
    ? "alert-panel warning"
    : "alert-panel healthy";

  const title = isCritical
    ? "緊急在庫アラート"
    : isWarning
    ? "在庫リスク通知"
    : "在庫状態正常";

  return (
    <div className={alertClass}>
      <div>
        <p className="alert-label">F-06 超過・不足警告アラート</p>
        <h2>{title}</h2>
        <p>{forecast.risk_message}</p>
      </div>

      <div className="alert-values">
        <span>現在庫：{forecast.current_stock.toLocaleString()}個</span>
        <span>安全在庫：{forecast.safety_stock.toLocaleString()}個</span>
        <span>推奨発注量：{forecast.recommended_order.toLocaleString()}個</span>
      </div>
    </div>
  );
}

export default AlertPanel;