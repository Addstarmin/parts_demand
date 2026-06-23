function KpiCard({ title, value, subText, type = "normal" }) {
  return (
    <div className={`kpi-card ${type}`}>
      <p className="kpi-title">{title}</p>
      <h2>{value}</h2>
      {subText && <p className="kpi-sub">{subText}</p>}
    </div>
  );
}

export default KpiCard;