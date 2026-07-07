import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import KpiCard from "../components/KpiCard";
import ForecastChart from "../components/ForecastChart";
import AlertPanel from "../components/AlertPanel";
import ShipmentPeakChart from "../components/ShipmentPeakChart";
import {
  getFactories,
  getForecast,
  getParts,
  runSimulation,
  getShipmentPeak,
} from "../services/api";

function Dashboard() {
  const [currentPage, setCurrentPage] = useState("dashboard");

  const [factories, setFactories] = useState([]);
  const [parts, setParts] = useState([]);

  const [selectedFactory, setSelectedFactory] = useState("");
  const [selectedPart, setSelectedPart] = useState("");

  const [forecast, setForecast] = useState(null);
  const [shipmentPeak, setShipmentPeak] = useState(null);

  const [simRate, setSimRate] = useState("");
  const [simResult, setSimResult] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // 初回マスタ読み込み
  useEffect(() => {
    const initData = async () => {
      try {
        setLoading(true);
        setError("");

        const [factoryData, partsData] = await Promise.all([
          getFactories(),
          getParts(),
        ]);

        setFactories(factoryData);
        setParts(partsData);

        if (factoryData.length > 0) {
          setSelectedFactory(factoryData[0].factory_id);
        }

        if (partsData.length > 0) {
          setSelectedPart(partsData[0].parts_id);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    initData();
  }, []);

  // 工場・部品変更時の需要予測およびJIT出荷ピークの並行取得 (IT-01 連携対応)
  useEffect(() => {
    if (!selectedFactory || !selectedPart) return;

    const loadForecastAndPeaks = async () => {
      try {
        setLoading(true);
        setError("");
        setSimResult("");
        setShipmentPeak(null);

        // 1. 基本需要予測データをフェッチ
        const forecastData = await getForecast(selectedFactory, selectedPart);
        setForecast(forecastData);

        // 為替レートの初期初期設定（本日のリアルタイム値を優先、なければ予測前提値）
        if (forecastData?.current_indicators?.usd_jpy) {
          setSimRate(forecastData.current_indicators.usd_jpy);
        } else if (forecastData?.indicators?.usd_jpy) {
          setSimRate(forecastData.indicators.usd_jpy);
        }

        // 2. 予測ボリュームに基づきJIT出荷ピーク予測を取得
        const peakData = await getShipmentPeak(
          selectedFactory,
          selectedPart,
          forecastData.next_week_forecast
        );
        setShipmentPeak(peakData);

      } catch (err) {
        setError(err.message);
        setForecast(null);
        setShipmentPeak(null);
      } finally {
        setLoading(false);
      }
    };

    loadForecastAndPeaks();
  }, [selectedFactory, selectedPart]);

  // 為替シミュレーション再計算処理のハンドリング拡張 (IT-01)
  const handleSimulation = async () => {
    setError("");
    setSimResult("");
    if (!forecast) return;

    try {
      setLoading(true);
      const result = await runSimulation({
        factoryId: selectedFactory,
        partsId: selectedPart,
        usdJpy: simRate,
      });

      setSimResult(result.message);

      // シミュレーション結果により動的スケーリングされた次週需要 (new_forecast) でJITピークも再計算
      if (result.new_forecast !== undefined) {
        const updatedPeakData = await getShipmentPeak(
          selectedFactory,
          selectedPart,
          result.new_forecast
        );
        setShipmentPeak(updatedPeakData);
        
        // 既存UIの予測整合性を保つため部分的なステート同期
        setForecast((prev) => ({
          ...prev,
          next_week_forecast: result.new_forecast,
          recommended_order: result.new_recommended_order,
        }));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const renderDashboard = () => (
    <>
      <div className="top-panel">
        <div>
          <p className="page-label">Dashboard</p>
          <h1>部品需要・在庫最適化AIダッシュボード</h1>
        </div>

        <div className="select-area">
          <select
            value={selectedFactory}
            onChange={(e) => setSelectedFactory(e.target.value)}
          >
            {factories.map((factory) => (
              <option key={factory.factory_id} value={factory.factory_id}>
                {factory.factory_name}
              </option>
            ))}
          </select>

          <select
            value={selectedPart}
            onChange={(e) => setSelectedPart(e.target.value)}
          >
            {parts.map((part) => (
              <option key={part.parts_id} value={part.parts_id}>
                {part.parts_id} {part.parts_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <div className="info-message">データ取得中...</div>}
      {error && <div className="error-message">{error}</div>}

      {forecast && (
        <>
          <AlertPanel forecast={forecast} />

          <section className="kpi-grid">
            <KpiCard
              title="発注推奨ステータス"
              value={forecast.risk_level}
              subText={forecast.risk_message}
              type={
                forecast.risk_level === "CRITICAL"
                  ? "danger"
                  : forecast.risk_level === "WARNING"
                  ? "warning"
                  : "normal"
              }
            />

            <KpiCard
              title="現在庫"
              value={`${forecast.current_stock.toLocaleString()}個`}
              subText={`安全在庫：${forecast.safety_stock.toLocaleString()}個`}
            />

            <KpiCard
              title="次週需要予測"
              value={`${forecast.next_week_forecast.toLocaleString()}個`}
              subText="AI予測値"
            />

            <KpiCard
              title="推奨発注量"
              value={`${forecast.recommended_order.toLocaleString()}個`}
              subText="今週中の発注を推奨"
              type="warning"
            />
          </section>

          <ForecastChart chartData={forecast.forecast_chart} />

          {/* F-07 JIT出荷ピーク予測積層チャートコンポーネントをレイアウト構造を維持して埋め込み */}
          {shipmentPeak && (
            <ShipmentPeakChart
              data={shipmentPeak.peak_data}
              peakInfo={shipmentPeak.peak_info}
            />
          )}

          {/* 🌟 修正ポイント：インジケーターを「過去の予測前提」と「本日」の計6つに拡張 */}
          <h3 style={{ margin: "20px 0 10px 0", color: "#4A5568" }}>外部経済指標・環境データ（全6項目）</h3>
          <section className="indicator-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "20px" }}>
            
            {/* 1. 過去の為替 */}
            <div className="info-card" style={{ borderLeft: "4px solid #4299e1" }}>
              <p style={{ color: "#718096", fontSize: "0.9rem" }}>ドル/円為替（予測前提）</p>
              <h2>{forecast.indicators?.usd_jpy ?? "-"}円</h2>
              <span>取得日：{forecast.indicators?.usd_jpy_date ?? "-"}</span>
            </div>

            {/* 2. 過去のPMI */}
            <div className="info-card" style={{ borderLeft: "4px solid #4299e1" }}>
              <p style={{ color: "#718096", fontSize: "0.9rem" }}>製造業PMI（予測前提）</p>
              <h2>{forecast.indicators?.pmi ?? "-"}</h2>
              <span>取得日：{forecast.indicators?.pmi_date ?? "-"}</span>
            </div>

            {/* 3. 過去の気象 */}
            <div className="info-card" style={{ borderLeft: "4px solid #4299e1" }}>
              <p style={{ color: "#718096", fontSize: "0.9rem" }}>気象情報（予測前提）</p>
              <h2>{forecast.indicators?.temperature ?? "-"}℃</h2>
              <span>
                予測：{forecast.forecast_chart?.slice(-1)[0]?.date ?? "-"}
                <br />
                {forecast.indicators?.weather_message ?? "-"}
              </span>
            </div>

            {/* 4. 本日の為替 */}
            <div className="info-card" style={{ borderLeft: "4px solid #48bb78" }}>
              <p style={{ color: "#2f855a", fontWeight: "bold", fontSize: "0.9rem" }}>🟢 本日のドル/円為替</p>
              <h2>{forecast.current_indicators?.usd_jpy ?? "-"}円</h2>
              <span>取得日：{forecast.current_indicators?.usd_jpy_date ?? "-"}</span>
            </div>

            {/* 5. 本日のPMI */}
            <div className="info-card" style={{ borderLeft: "4px solid #48bb78" }}>
              <p style={{ color: "#2f855a", fontWeight: "bold", fontSize: "0.9rem" }}>🟢 最新の製造業PMI</p>
              <h2>{forecast.current_indicators?.pmi ?? "-"}</h2>
              <span>取得日：{forecast.current_indicators?.pmi_date ?? "-"}</span>
            </div>

            {/* 6. 本日の気象 */}
            <div className="info-card" style={{ borderLeft: "4px solid #48bb78" }}>
              <p style={{ color: "#2f855a", fontWeight: "bold", fontSize: "0.9rem" }}>🟢 本日の気象情報</p>
              <h2>{forecast.current_indicators?.temperature ?? "-"}℃</h2>
              <span>
                ステータス：
                <br />
                {forecast.current_indicators?.weather_message ?? "-"}
              </span>
            </div>

          </section>
        </>
      )}
    </>
  );

  const renderDetail = () => (
    <div className="content-card">
      <p className="section-label">Detail</p>
      <h2>詳細分析</h2>

      {forecast ? (
        <>
          <p>
            選択中の部品：
            <strong>
              {forecast.parts_id} {forecast.parts_name}
            </strong>
          </p>

          <div className="detail-grid">
            <div>
              <h3>需要変動の要因</h3>
              <p>過去の実績データと本日のリアルタイム指標を比較・分析しています。</p>
              <h4 style={{ margin: "10px 0 5px 0" }}>【予測モデル適用値】</h4>
              <p>ドル円：{forecast.indicators?.usd_jpy}円 / PMI：{forecast.indicators?.pmi} / 気温：{forecast.indicators?.temperature}℃</p>
              
              <h4 style={{ margin: "10px 0 5px 0", color: "#2f855a" }}>【本日リアルタイム値】</h4>
              <p>ドル円：{forecast.current_indicators?.usd_jpy}円 / PMI：{forecast.current_indicators?.pmi} / 気温：{forecast.current_indicators?.temperature}℃</p>
            </div>

            <div>
              <h3>リスク判定</h3>
              <p>{forecast.risk_message}</p>
              <p>現在庫：{forecast.current_stock.toLocaleString()}個</p>
              <p>安全在庫：{forecast.safety_stock.toLocaleString()}個</p>
            </div>
          </div>
        </>
      ) : (
        <p>データを取得してください。</p>
      )}
    </div>
  );

  const renderParts = () => (
    <div className="content-card">
      <p className="section-label">Parts</p>
      <h2>部品情報</h2>

      <table>
        <thead>
          <tr>
            <th>部品ID</th>
            <th>部品名</th>
            <th>リードタイム</th>
            <th>安全在庫日数</th>
          </tr>
        </thead>
        <tbody>
          {parts.map((part) => (
            <tr key={part.parts_id}>
              <td>{part.parts_id}</td>
              <td>{part.parts_name}</td>
              <td>{part.lead_time_weeks}週</td>
              <td>{part.safety_stock_days}日</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderSimulation = () => (
    <div className="content-card">
      <p className="section-label">Simulation</p>
      <h2>為替シミュレーション</h2>

      {forecast ? (
        <div className="simulation-box">
          <label>対象工場</label>
          <input value={forecast.factory_name} disabled />

          <label>対象部品</label>
          <input value={`${forecast.parts_id} ${forecast.parts_name}`} disabled />

          <label>現在のリアルタイム為替レート</label>
          <input value={`${forecast.current_indicators?.usd_jpy ?? forecast.indicators?.usd_jpy} 円`} disabled />

          <label>シミュレーション用ドル円レート</label>
          <input
            type="number"
            value={simRate}
            onChange={(e) => setSimRate(e.target.value)}
          />

          <button onClick={handleSimulation}>予測を再計算する</button>

          {simResult && <div className="success-message">{simResult}</div>}
          {error && <div className="error-message">{error}</div>}
        </div>
      ) : (
        <p>先にダッシュボードでデータを取得してください。</p>
      )}
    </div>
  );

  const renderSettings = () => (
    <div className="content-card">
      <p className="section-label">Settings</p>
      <h2>設定</h2>
      <p>API接続先：localhost:8000</p>
    </div>
  );

  const renderContent = () => {
    if (currentPage === "dashboard") return renderDashboard();
    if (currentPage === "detail") return renderDetail();
    if (currentPage === "parts") return renderParts();
    if (currentPage === "simulation") return renderSimulation();
    if (currentPage === "settings") return renderSettings();

    return renderDashboard();
  };

  return (
    <div className="app-layout">
      <Sidebar currentPage={currentPage} setCurrentPage={setCurrentPage} />
      <main className="main-content">{renderContent()}</main>
    </div>
  );
}

export default Dashboard;