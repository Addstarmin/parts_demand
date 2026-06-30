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

        if (factoryData.length > 0) setSelectedFactory(factoryData[0].factory_id);
        if (partsData.length > 0) setSelectedPart(partsData[0].parts_id);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    initData();
  }, []);

  useEffect(() => {
    if (!selectedFactory || !selectedPart) return;

    const loadForecast = async () => {
      try {
        setLoading(true);
        setError("");
        setSimResult("");
        setShipmentPeak(null);

        const data = await getForecast(selectedFactory, selectedPart);
        setForecast(data);

        const peakData = await getShipmentPeak(
          selectedFactory,
          selectedPart,
          data.next_week_forecast
        );
        setShipmentPeak(peakData);

        if (data?.indicators?.usd_jpy) {
          setSimRate(data.indicators.usd_jpy);
        }
      } catch (err) {
        setError(err.message);
        setForecast(null);
        setShipmentPeak(null);
      } finally {
        setLoading(false);
      }
    };

    loadForecast();
  }, [selectedFactory, selectedPart]);

  const handleSimulation = async () => {
    setError("");
    setSimResult("");
    try {
      const result = await runSimulation({
        factoryId: selectedFactory,
        partsId: selectedPart,
        usdJpy: simRate,
      });
      setSimResult(result.message);
    } catch (err) {
      setError(err.message);
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

      {loading && <div className="info-message">データ同期中...</div>}
      {error && <div className="error-message">{error}</div>}

      {forecast && (
        <>
          <AlertPanel forecast={forecast} />

          {/* KPI表示エリア：すべての予測項目（4つ）を過不足なく統合表示 */}
          <section className="kpi-grid">
            <KpiCard
              title="① 次週 需要予測"
              value={`${forecast.next_week_forecast.toLocaleString()} 個`}
              subText="マクロ環境連動AI予測値"
            />

            <KpiCard
              title="② 推奨発注量"
              value={`${forecast.recommended_order.toLocaleString()} 個`}
              subText="調達・サプライヤへの推奨手配量"
              type="warning"
            />

            <KpiCard
              title="③ 推奨生産指示量"
              value={`${forecast.recommended_production.toLocaleString()} 個`}
              subText="安全在庫維持に必要な製造ライン枠"
              type={forecast.recommended_production > 0 ? "warning" : "normal"}
            />

            <KpiCard
              title="④ 推奨出荷・引取枠"
              value={`${forecast.recommended_shipping.toLocaleString()} 個`}
              subText="次週JIT要求に基づく総出荷量"
            />
          </section>

          <ForecastChart chartData={forecast.forecast_chart} />

          {shipmentPeak && (
            <ShipmentPeakChart
              data={shipmentPeak.peak_data}
              peakInfo={shipmentPeak.peak_info}
            />
          )}

          <section className="indicator-grid">
            <div className="info-card">
              <p>ドル/円為替</p>
              <h2>{forecast.indicators.usd_jpy} 円</h2>
              <span>Frankfurter / ER API リアルタイム連携</span>
            </div>

            <div className="info-card">
              <p>製造業景気指数 (PMI)</p>
              <h2>{forecast.indicators.pmi}</h2>
              <span>FREDマクロ経済データ指標</span>
            </div>

            <div className="info-card">
              <p>工場周辺の気象情報</p>
              <h2>{forecast.indicators.temperature} ℃</h2>
              <span>{forecast.indicators.weather_message}</span>
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
          <p>選択中の部品：<strong>{forecast.parts_id} {forecast.parts_name}</strong></p>
          <div className="detail-grid">
            <div>
              <h3>需要変動のマクロ要因</h3>
              <p>ドル円レート：{forecast.indicators.usd_jpy} 円</p>
              <p>製造業PMI：{forecast.indicators.pmi}</p>
              <p>拠点付近気温：{forecast.indicators.temperature} ℃</p>
            </div>
            <div>
              <h3>リスクアセスメント</h3>
              <p>{forecast.risk_message}</p>
              <p>現在庫：{forecast.current_stock.toLocaleString()} 個</p>
              <p>安全在庫目標：{forecast.safety_stock.toLocaleString()} 個</p>
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
      <h2>部品情報マスタ</h2>
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
              <td>{part.lead_time_weeks} 週</td>
              <td>{part.safety_stock_days} 日</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderSimulation = () => (
    <div className="content-card">
      <p className="section-label">Simulation</p>
      <h2>為替連動 需要感度シミュレーション</h2>
      {forecast ? (
        <div className="simulation-box">
          <label>対象工場拠点</label>
          <input value={forecast.factory_name} disabled />
          <label>対象構成部品</label>
          <input value={`${forecast.parts_id} ${forecast.parts_name}`} disabled />
          <label>基準ドル円レート</label>
          <input value={`${forecast.indicators.usd_jpy} 円`} disabled />
          <label>仮想変更レート（1ドルあたり）</label>
          <input
            type="number"
            value={simRate}
            onChange={(e) => setSimRate(e.target.value)}
          />
          <button onClick={handleSimulation}>感度シミュレーション再計算</button>
          {simResult && <div className="success-message">{simResult}</div>}
          {error && <div className="error-message">{error}</div>}
        </div>
      ) : (
        <p>ダッシュボード画面から対象データを選択してください。</p>
      )}
    </div>
  );

  const renderSettings = () => (
    <div className="content-card">
      <p className="section-label">Settings</p>
      <h2>システム環境設定</h2>
      <p>APIゲートウェイエンドポイント：http://localhost:8000/api</p>
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