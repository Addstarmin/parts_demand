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
  productForecast,
} from "../services/api";

function Dashboard() {
  const [currentPage, setCurrentPage] = useState("dashboard");
  const [factories, setFactories] = useState([]);
  const [parts, setParts] = useState([]);
  const [selectedFactory, setSelectedFactory] = useState("");
  const [selectedPart, setSelectedPart] = useState("");
  const [targetType, setTargetType] = useState("part");
  const [selectedProduct, setSelectedProduct] = useState("PROD-A");
  const [productParts, setProductParts] = useState([]);
  const [productForecastData, setProductForecastData] = useState(null);
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

  useEffect(() => {
    if (!selectedFactory || !selectedPart) return;
    if (targetType !== "part") return;

    const loadForecast = async () => {
      try {
        if (targetType !== "part") {
          setLoading(false);
        return;
        }

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
  }, [selectedFactory, selectedPart, targetType]);

　const handleProductForecast = async () => {
    try {
      setError("");
      setProductParts([]);
      setProductForecastData(null);

      const result = await productForecast(selectedProduct, 100);

      setProductForecastData(result);
      setProductParts(result.parts);

      console.log("product forecast:", result);
    } catch (err) {
      setError(err.message);
    }
  };

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

          <div>
            <label>
              <input
                type="radio"
                value="part"
                checked={targetType === "part"}
                onChange={() => {
                  setTargetType("part");
                  setProductParts([]);
                }}
              />
              部品
            </label>

            <label>
              <input
                type="radio"
                value="product"
                checked={targetType === "product"}
                onChange={() => {
                  setTargetType("product");
                  setForecast(null);
                  setShipmentPeak(null);
                  setProductParts([]);
                  setProductForecastData(null);
                  setLoading(false);
                }}
              />
              製品
            </label>
          </div>

          {targetType === "part" ? (
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
          ) : (
            <>
              <select
                value={selectedProduct}
                onChange={(e) => setSelectedProduct(e.target.value)}
              >
                <option value="PROD-A">PROD-A キャブレターASSY</option>
                <option value="PROD-B">PROD-B エンジンASSY</option>
              </select>

              <button onClick={handleProductForecast}>製品を部品展開</button>
            </>
          )}
        </div>
      </div>

      {loading && <div className="info-message">データ取得中...</div>}
      {error && <div className="error-message">{error}</div>}

      {targetType === "product" && productParts.length > 0 && (
        <div className="content-card">
          <h2>製品アセンブリ構成部品</h2>
          <p>{selectedProduct} を100個生産する場合の必要部品数</p>

          <table>
            <thead>
              <tr>
                <th>部品ID</th>
                <th>必要数</th>
              </tr>
            </thead>
            <tbody>
              {productParts.map((item) => (
                <tr key={item.parts_id}>
                  <td>{item.parts_id}</td>
                  <td>{item.quantity}個</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {targetType === "product" && productForecastData && (
      <ForecastChart chartData={productForecastData.forecast_chart} />
      )}

      {forecast && targetType === "part" && (
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

          {shipmentPeak && (
            <ShipmentPeakChart
              data={shipmentPeak.peak_data}
              peakInfo={shipmentPeak.peak_info}
            />
          )}

          <section className="indicator-grid">
            <div className="info-card">
              <p>ドル/円為替</p>
              <h2>{forecast.indicators.usd_jpy}円</h2>
              <span>リアルタイム為替API</span>
            </div>

            <div className="info-card">
              <p>製造業PMI</p>
              <h2>{forecast.indicators.pmi}</h2>
              <span>50以上なら好景気傾向</span>
            </div>

            <div className="info-card">
              <p>気象情報</p>
              <h2>{forecast.indicators.temperature}℃</h2>
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
          <p>
            選択中の部品：
            <strong>
              {forecast.parts_id} {forecast.parts_name}
            </strong>
          </p>

          <div className="detail-grid">
            <div>
              <h3>需要変動の要因</h3>
              <p>
                為替、PMI、気象データを組み合わせて需要変動を分析しています。
              </p>
              <p>ドル円：{forecast.indicators.usd_jpy}円</p>
              <p>PMI：{forecast.indicators.pmi}</p>
              <p>気温：{forecast.indicators.temperature}℃</p>
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

          <label>現在のドル円レート</label>
          <input value={forecast.indicators.usd_jpy} disabled />

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