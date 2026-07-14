import { useEffect, useState } from "react";
import { getProductionNoticeHistory, runProductionNotice } from "../services/api";
import DecisionSummary from "./DecisionSummary";
import ForecastChart from "./ForecastChart";
import SimulationHistory from "./SimulationHistory";

function ProductionNoticeSimulator({ factoryId, products, manufacturers, onResult }) {
  const [manufacturerId, setManufacturerId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [rate, setRate] = useState(-20);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getProductionNoticeHistory().then(setHistory).catch(() => setHistory([]));
  }, []);

  const effectiveManufacturerId = manufacturerId || manufacturers[0]?.manufacturer_id || "";
  const effectiveTargetId = targetId || products[0]?.product_id || "";

  const execute = async () => {
    try {
      setLoading(true);
      setError("");
      const data = await runProductionNotice({
        factoryId,
        manufacturerId: effectiveManufacturerId,
        adjustmentRate: rate,
        targetType: "product",
        targetId: effectiveTargetId,
      });
      setResult(data);
      onResult?.(data);
      setHistory(await getProductionNoticeHistory());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="content-card">
        <div className="section-header">
          <div>
            <p className="section-label">F-05</p>
            <h2>完成車メーカー別増減産内示シミュレーター</h2>
          </div>
          <span className={`badge ${rate < 0 ? "danger-badge" : rate > 0 ? "success-badge" : ""}`}>
            {rate < 0 ? "減産" : rate > 0 ? "増産" : "変更なし"}
          </span>
        </div>
        <div className="form-grid">
          <label>
            完成車メーカー
            <select value={effectiveManufacturerId} onChange={(e) => setManufacturerId(e.target.value)}>
              {manufacturers.map((m) => (
                <option key={m.manufacturer_id} value={m.manufacturer_id}>
                  {m.manufacturer_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            対象製品
            <select value={effectiveTargetId} onChange={(e) => setTargetId(e.target.value)}>
              <option value="">メーカー紐づき全製品</option>
              {products.map((p) => (
                <option key={p.product_id} value={p.product_id}>
                  {p.product_id} {p.product_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            調整率（%）
            <input type="number" min="-50" max="50" value={rate} onChange={(e) => setRate(Number(e.target.value))} />
          </label>
          <label>
            スライダー
            <input type="range" min="-50" max="50" value={rate} onChange={(e) => setRate(Number(e.target.value))} />
          </label>
        </div>
        <div className="button-row">
          <button onClick={() => setRate(0)} disabled={loading}>0%へ戻す</button>
          <button onClick={execute} disabled={loading || !factoryId || !effectiveManufacturerId}>
            {loading ? "計算中..." : "シミュレーション実行"}
          </button>
        </div>
        {error && <div className="error-message">{error}</div>}
      </div>
      <DecisionSummary result={result} />
      {result && <ForecastChart chartData={result.forecast_chart} title="通常予測と内示調整後予測" />}
      {result?.affected_parts?.length > 0 && (
        <div className="content-card">
          <h2>対象となる部品影響</h2>
          <table>
            <thead>
              <tr>
                <th>部品</th>
                <th>通常需要</th>
                <th>調整後需要</th>
                <th>差分</th>
                <th>対象製品</th>
              </tr>
            </thead>
            <tbody>
              {result.affected_parts.map((part) => (
                <tr key={part.parts_id}>
                  <td>{part.parts_id} {part.parts_name}</td>
                  <td>{Number(part.normal_demand).toLocaleString()}個</td>
                  <td>{Number(part.adjusted_demand).toLocaleString()}個</td>
                  <td>{Number(part.difference).toLocaleString()}個</td>
                  <td>{part.source_products.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <SimulationHistory history={history} />
    </>
  );
}

export default ProductionNoticeSimulator;
