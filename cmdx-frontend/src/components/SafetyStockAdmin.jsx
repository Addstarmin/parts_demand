import { useEffect, useState } from "react";
import {
  getSafetyStockCurrent,
  getSafetyStockHistory,
  getSafetyStockSettings,
  optimizeSafetyStock,
  previewSafetyStock,
  saveSafetyStockSettings,
} from "../services/api";
import SafetyStockHistoryTable from "./SafetyStockHistoryTable";

const fmt = (value) => Number(value || 0).toLocaleString();

function SafetyStockAdmin() {
  const [settings, setSettings] = useState(null);
  const [current, setCurrent] = useState([]);
  const [preview, setPreview] = useState(null);
  const [history, setHistory] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [settingsData, currentData, historyData] = await Promise.all([
        getSafetyStockSettings(),
        getSafetyStockCurrent(),
        getSafetyStockHistory(),
      ]);
      setSettings(settingsData);
      setCurrent(currentData);
      setHistory(historyData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const update = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: Number(value) }));
  };

  const save = async () => {
    try {
      setLoading(true);
      setMessage("");
      setSettings(await saveSafetyStockSettings(settings));
      setMessage("設定を保存しました。");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const runPreview = async () => {
    try {
      setLoading(true);
      setPreview(await previewSafetyStock());
      setMessage("プレビューを更新しました。");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const runOptimize = async () => {
    if (!window.confirm("安全在庫マスタを更新します。実行しますか？")) return;
    try {
      setLoading(true);
      const result = await optimizeSafetyStock();
      setPreview(result);
      setMessage(
        `最適化完了：成功${result.summary.total}件、増加${result.summary.increase}件、減少${result.summary.decrease}件、変更なし${result.summary.unchanged}件`
      );
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!settings) return <div className="info-message">安全在庫設定を読み込み中...</div>;

  return (
    <>
      <div className="content-card">
        <div className="section-header">
          <div>
            <p className="section-label">F-08</p>
            <h2>安全在庫マスタ動的最適化</h2>
          </div>
          <span className="badge">Asia/Tokyo 月初0:00想定</span>
        </div>
        {loading && <div className="info-message">処理中...</div>}
        {message && <div className="success-message">{message}</div>}
        {error && <div className="error-message">{error}</div>}
        <div className="form-grid">
          <label>安全係数<input type="number" step="0.05" min="0.1" max="5" value={settings.default_safety_factor} onChange={(e) => update("default_safety_factor", e.target.value)} /></label>
          <label>評価期間（月）<input type="number" min="1" max="12" value={settings.evaluation_months} onChange={(e) => update("evaluation_months", e.target.value)} /></label>
          <label>安全在庫最小値<input type="number" min="0" value={settings.min_safety_stock} onChange={(e) => update("min_safety_stock", e.target.value)} /></label>
          <label>安全在庫最大値<input type="number" min="0" value={settings.max_safety_stock} onChange={(e) => update("max_safety_stock", e.target.value)} /></label>
          <label>最大変更率<input type="number" step="0.05" min="0" max="1" value={settings.max_change_rate} onChange={(e) => update("max_change_rate", e.target.value)} /></label>
          <label>要確認変更率<input type="number" step="0.05" min="0" max="1" value={settings.review_threshold_rate} onChange={(e) => update("review_threshold_rate", e.target.value)} /></label>
        </div>
        <div className="button-row">
          <button disabled={loading} onClick={save}>設定保存</button>
          <button disabled={loading} onClick={runPreview}>プレビュー実行</button>
          <button disabled={loading} onClick={runOptimize}>今すぐ最適化</button>
        </div>
        <p className="note">式: ceil(安全係数 × RMSE × sqrt(リードタイム日数 / 7))。1回の更新は旧値から最大±{Math.round(settings.max_change_rate * 100)}%に制限します。</p>
        <p className="note">最終実行: {preview?.last_executed_at || "未実行"} / 次回予定: {preview?.next_run_at || "月初0:00 JST"}</p>
      </div>
      <div className="content-card">
        <h2>現在の安全在庫一覧</h2>
        <table>
          <thead>
            <tr><th>工場</th><th>部品</th><th>現在庫</th><th>安全在庫</th><th>RMSE</th><th>LT</th><th>更新日</th></tr>
          </thead>
          <tbody>
            {current.map((item) => (
              <tr key={`${item.factory_id}-${item.parts_id}`}>
                <td>{item.factory_id}</td>
                <td>{item.parts_id} {item.parts_name}</td>
                <td>{fmt(item.current_stock)}個</td>
                <td>{fmt(item.safety_stock_quantity)}個</td>
                <td>{fmt(item.rmse)}</td>
                <td>{item.lead_time_days}日</td>
                <td>{item.updated_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {preview && (
        <div className="content-card">
          <div className="section-header">
            <div><p className="section-label">Preview</p><h2>新旧差分一覧</h2></div>
            <span className="badge">増加{preview.summary.increase} / 減少{preview.summary.decrease} / 変更なし{preview.summary.unchanged}</span>
          </div>
          <table>
            <thead>
              <tr><th>工場</th><th>部品</th><th>旧安全在庫</th><th>新安全在庫</th><th>差</th><th>変化率</th><th>RMSE</th><th>LT</th><th>判定</th><th>変更理由</th></tr>
            </thead>
            <tbody>
              {preview.items.map((item) => (
                <tr key={`${item.factory_id}-${item.parts_id}`}>
                  <td>{item.factory_id}</td>
                  <td>{item.parts_id}</td>
                  <td>{fmt(item.old_safety_stock)}個</td>
                  <td>{fmt(item.new_safety_stock)}個</td>
                  <td>{fmt(item.difference)}個</td>
                  <td>{Math.round(item.difference_rate * 100)}%</td>
                  <td>{item.rmse}</td>
                  <td>{item.lead_time_days}日</td>
                  <td><span className={`status-badge ${item.status === "増加" ? "up" : item.status === "減少" ? "down" : ""}`}>{item.needs_review ? "要確認" : item.status}</span></td>
                  <td>{item.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <SafetyStockHistoryTable history={history} />
    </>
  );
}

export default SafetyStockAdmin;
