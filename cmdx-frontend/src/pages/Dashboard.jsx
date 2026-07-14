import { useEffect, useMemo, useState } from "react";
import Sidebar from "../components/Sidebar";
import KpiCard from "../components/KpiCard";
import ForecastChart from "../components/ForecastChart";
import AlertPanel from "../components/AlertPanel";
import ShipmentPeakChart from "../components/ShipmentPeakChart";
import TargetSelector from "../components/TargetSelector";
import ProductBomTable from "../components/ProductBomTable";
import ProductionNoticeSimulator from "../components/ProductionNoticeSimulator";
import SafetyStockAdmin from "../components/SafetyStockAdmin";
import {
  getFactories,
  getForecast,
  getManufacturers,
  getParts,
  getProductForecast,
  getProducts,
  getShipmentPeak,
  downloadActualHistoryCsv,
  downloadForecastCsv,
  downloadFutureActualTemplateCsv,
  runSimulation,
} from "../services/api";

const fmt = (value) => Number(value || 0).toLocaleString();

function Dashboard() {
  const [currentPage, setCurrentPage] = useState("dashboard");
  const [factories, setFactories] = useState([]);
  const [parts, setParts] = useState([]);
  const [products, setProducts] = useState([]);
  const [manufacturers, setManufacturers] = useState([]);
  const [selectedFactory, setSelectedFactory] = useState("");
  const [selectedPart, setSelectedPart] = useState("");
  const [selectedProduct, setSelectedProduct] = useState("");
  const [targetType, setTargetType] = useState("part");
  const [productView, setProductView] = useState("product");
  const [selectedComponent, setSelectedComponent] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [productForecast, setProductForecast] = useState(null);
  const [shipmentPeak, setShipmentPeak] = useState(null);
  const [noticeResult, setNoticeResult] = useState(null);
  const [simRate, setSimRate] = useState("");
  const [simResult, setSimResult] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const initData = async () => {
      try {
        setLoading(true);
        setError("");
        const [factoryData, partsData, manufacturerData] = await Promise.all([
          getFactories(),
          getParts(),
          getManufacturers(),
        ]);
        setFactories(factoryData);
        setParts(partsData);
        setManufacturers(manufacturerData);
        setSelectedFactory(factoryData[1]?.factory_id || factoryData[0]?.factory_id || "");
        setSelectedPart(partsData[0]?.parts_id || "");
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    initData();
  }, []);

  useEffect(() => {
    if (!selectedFactory) return;
    getProducts(selectedFactory)
      .then((data) => {
        setProducts(data);
        setSelectedProduct((prev) => (data.some((item) => item.product_id === prev) ? prev : data[0]?.product_id || ""));
      })
      .catch((err) => setError(err.message));
  }, [selectedFactory]);

  useEffect(() => {
    if (!selectedFactory) return;
    const loadForecast = async () => {
      try {
        setLoading(true);
        setError("");
        setNoticeResult(null);
        setSelectedComponent(null);
        if (targetType === "part") {
          if (!selectedPart) return;
          const data = await getForecast(selectedFactory, selectedPart);
          setForecast(data);
          setProductForecast(null);
          const peakData = await getShipmentPeak(selectedFactory, selectedPart, data.next_week_forecast);
          setShipmentPeak(peakData);
          if (data?.indicators?.usd_jpy) setSimRate(data.indicators.usd_jpy);
        } else {
          if (!selectedProduct) return;
          const data = await getProductForecast(selectedFactory, selectedProduct);
          setProductForecast(data);
          setForecast(null);
          setShipmentPeak(null);
        }
      } catch (err) {
        setError(err.message);
        setForecast(null);
        setProductForecast(null);
        setShipmentPeak(null);
      } finally {
        setLoading(false);
      }
    };
    loadForecast();
  }, [selectedFactory, selectedPart, selectedProduct, targetType]);

  const displayChart = useMemo(() => {
    if (targetType === "part") return noticeResult?.forecast_chart || forecast?.forecast_chart;
    if (productView === "components" && selectedComponent) return selectedComponent.forecast_chart;
    return noticeResult?.forecast_chart || productForecast?.forecast_chart;
  }, [targetType, productView, selectedComponent, noticeResult, forecast, productForecast]);

  const handleSimulation = async () => {
    try {
      setError("");
      setSimResult("");
      const result = await runSimulation({ factoryId: selectedFactory, partsId: selectedPart, usdJpy: simRate });
      setSimResult(result.message);
    } catch (err) {
      setError(err.message);
    }
  };

  const currentTargetId = targetType === "product" ? selectedProduct : selectedPart;

  const renderDownloadPanel = () => (
    <div className="content-card">
      <div className="section-header">
        <div>
          <p className="section-label">CSV Export</p>
          <h2>実績・予測データのCSVダウンロード</h2>
        </div>
        <span className="badge">選択中: {currentTargetId || "-"}</span>
      </div>
      <div className="button-row">
        <button
          onClick={() => downloadActualHistoryCsv({ factoryId: selectedFactory, targetType, targetId: currentTargetId })}
          disabled={!selectedFactory || !currentTargetId}
        >
          これまでの実績CSV
        </button>
        <button
          onClick={() => downloadForecastCsv({ factoryId: selectedFactory, targetType, targetId: currentTargetId })}
          disabled={!selectedFactory || !currentTargetId}
        >
          予測値CSV
        </button>
        <button
          onClick={() => downloadFutureActualTemplateCsv({ factoryId: selectedFactory, targetType, targetId: currentTargetId })}
          disabled={!selectedFactory || !currentTargetId}
        >
          今後の実績入力テンプレートCSV
        </button>
      </div>
      <p className="note">実績CSVは過去データ、予測CSVは現在表示中の予測と推奨量、テンプレートCSVは今後の実績を追記するための形式です。</p>
    </div>
  );

  const renderEvaluation = (evaluation) => {
    if (!evaluation) return null;
    return (
      <div className="content-card">
        <div className="section-header">
          <div>
            <p className="section-label">Model Evaluation</p>
            <h2>AIモデル評価</h2>
          </div>
          <span className="badge">Prophet 0.4 / XGBoost 0.6</span>
        </div>
        <div className="metric-grid">
          <div><span>Prophet RMSE</span><strong>{evaluation.prophet_rmse ?? "-"}</strong></div>
          <div><span>XGBoost RMSE</span><strong>{evaluation.xgboost_rmse ?? "-"}</strong></div>
          <div><span>アンサンブルRMSE</span><strong>{evaluation.ensemble_rmse ?? "-"}</strong></div>
          <div><span>MAE</span><strong>{evaluation.mae ?? "-"}</strong></div>
          <div><span>評価期間</span><strong>{evaluation.evaluation_period || "-"}</strong></div>
          <div><span>学習データ件数</span><strong>{fmt(evaluation.training_records)}件</strong></div>
        </div>
        {evaluation.warning && <p className="note">{evaluation.warning}</p>}
      </div>
    );
  };

  const renderIndicators = (indicators) => {
    if (!indicators) return null;
    return (
      <section className="indicator-grid">
        <div className="info-card">
          <p>ドル/円為替</p>
          <h2>{indicators.usd_jpy}円</h2>
          <span>外部APIリアルタイム取得: {indicators.usd_jpy_source || "fallback"}</span>
        </div>
        <div className="info-card">
          <p>製造業PMI指数</p>
          <h2>{indicators.pmi}</h2>
          <span>取得日: {indicators.pmi_date}</span>
        </div>
        <div className="info-card">
          <p>気象データ</p>
          <h2>{indicators.temperature}℃</h2>
          <span>{indicators.weather_message}</span>
        </div>
      </section>
    );
  };

  const renderDashboard = () => (
    <>
      <div className="top-panel">
        <div>
          <p className="page-label">Dashboard</p>
          <h1>CMD-X 部品需要・在庫最適化AIダッシュボード</h1>
        </div>
        <TargetSelector
          factories={factories}
          parts={parts}
          products={products}
          selectedFactory={selectedFactory}
          selectedPart={selectedPart}
          selectedProduct={selectedProduct}
          targetType={targetType}
          onFactoryChange={setSelectedFactory}
          onPartChange={setSelectedPart}
          onProductChange={setSelectedProduct}
          onTargetTypeChange={setTargetType}
        />
      </div>
      {loading && <div className="info-message">データ取得中...</div>}
      {error && <div className="error-message">{error}</div>}
      {targetType === "part" && forecast && (
        <>
          <AlertPanel forecast={forecast} />
          <section className="kpi-grid">
            <KpiCard title="発注推奨ステータス" value={forecast.risk_level} subText={forecast.risk_message} type={forecast.risk_level === "CRITICAL" ? "danger" : forecast.risk_level === "WARNING" ? "warning" : "normal"} />
            <KpiCard title="部品需要" value={`${fmt(forecast.parts_demand ?? forecast.next_week_forecast)}個`} subText="次週AI予測値" />
            <KpiCard title="生産推奨量" value={`${fmt(forecast.recommended_production)}個`} subText={`現在庫：${fmt(forecast.current_stock)}個`} />
            <KpiCard title="発注推奨量" value={`${fmt(forecast.recommended_order)}個`} subText="安全在庫反映済み" type="warning" />
            <KpiCard title="出荷推奨量" value={`${fmt(forecast.recommended_shipping)}個`} subText={`倉庫上限目安：${fmt(forecast.warehouse_capacity)}個`} />
          </section>
          {forecast.safety_stock_detail && (
            <div className="content-card">
              <h2>動的安全在庫の根拠</h2>
              <div className="metric-grid">
                <div><span>現在値</span><strong>{fmt(forecast.safety_stock)}個</strong></div>
                <div><span>前回値</span><strong>{fmt(forecast.safety_stock_detail.previous_safety_stock)}個</strong></div>
                <div><span>変化率</span><strong>{Math.round((forecast.safety_stock_detail.change_rate || 0) * 100)}%</strong></div>
                <div><span>RMSE</span><strong>{forecast.safety_stock_detail.rmse ?? "-"}</strong></div>
                <div><span>LT</span><strong>{forecast.safety_stock_detail.lead_time_days ?? "-"}日</strong></div>
                <div><span>安全係数</span><strong>{forecast.safety_stock_detail.safety_factor ?? "-"}</strong></div>
              </div>
            </div>
          )}
          {renderIndicators(forecast.current_indicators || forecast.indicators)}
        </>
      )}
      {targetType === "product" && productForecast && (
        <>
          <section className="kpi-grid">
            <KpiCard title="製品需要" value={`${fmt(productForecast.next_week_forecast)}個`} subText={`${productForecast.product_id} ${productForecast.product_name}`} />
            <KpiCard title="生産推奨量" value={`${fmt(productForecast.recommended_production)}個`} subText={`製品換算在庫：${fmt(productForecast.current_stock)}個`} />
            <KpiCard title="発注推奨量" value={`${fmt(productForecast.recommended_order)}個`} subText={`動的安全在庫：${fmt(productForecast.safety_stock)}個`} type="warning" />
            <KpiCard title="出荷推奨量" value={`${fmt(productForecast.recommended_shipping)}個`} subText={productForecast.manufacturer_name || "架空デモデータ"} />
          </section>
          <AlertPanel forecast={productForecast} />
          <div className="segmented content-tabs">
            <button className={productView === "product" ? "active" : ""} onClick={() => setProductView("product")}>製品需要</button>
            <button className={productView === "components" ? "active" : ""} onClick={() => setProductView("components")}>構成部品別</button>
          </div>
          {productView === "components" && <ProductBomTable components={productForecast.component_forecasts} onSelectPart={setSelectedComponent} />}
          {renderIndicators(productForecast.current_indicators || productForecast.indicators)}
        </>
      )}
      {displayChart && <ForecastChart chartData={displayChart} title={selectedComponent ? `${selectedComponent.parts_id} 4週間予測` : "4週間需要予測"} />}
      {shipmentPeak && targetType === "part" && <ShipmentPeakChart data={shipmentPeak.peak_data} peakInfo={shipmentPeak.peak_info} />}
      {renderDownloadPanel()}
      {renderEvaluation(targetType === "product" ? productForecast?.model_evaluation : forecast?.model_evaluation)}
    </>
  );

  const renderDetail = () => (
    <div className="content-card">
      <p className="section-label">Detail</p>
      <h2>詳細分析</h2>
      <p>時系列分割で後半20%を評価し、Prophet系トレンド/季節性、XGBoost系ラグ特徴、0.4/0.6アンサンブルを比較します。</p>
      {renderEvaluation(targetType === "product" ? productForecast?.model_evaluation : forecast?.model_evaluation)}
    </div>
  );

  const renderParts = () => (
    <div className="content-card">
      <p className="section-label">Parts</p>
      <h2>部品情報</h2>
      <table>
        <thead><tr><th>部品ID</th><th>部品名</th><th>リードタイム</th><th>安全在庫日数</th><th>動的安全在庫</th></tr></thead>
        <tbody>
          {parts.map((part) => (
            <tr key={part.parts_id}>
              <td>{part.parts_id}</td><td>{part.parts_name}</td><td>{part.lead_time_weeks}週</td><td>{part.safety_stock_days}日</td><td>{part.safety_stock_quantity ? `${fmt(part.safety_stock_quantity)}個` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderSimulation = () => (
    <>
      <ProductionNoticeSimulator factoryId={selectedFactory} products={products} manufacturers={manufacturers} onResult={setNoticeResult} />
      <div className="content-card">
        <p className="section-label">Legacy</p>
        <h2>為替シミュレーション</h2>
        {forecast ? (
          <div className="simulation-box">
            <label>対象工場<input value={forecast.factory_name} disabled /></label>
            <label>対象部品<input value={`${forecast.parts_id} ${forecast.parts_name}`} disabled /></label>
            <label>シミュレーション用ドル円レート<input type="number" value={simRate} onChange={(e) => setSimRate(e.target.value)} /></label>
            <button onClick={handleSimulation}>予測を再計算する</button>
            {simResult && <div className="success-message">{simResult}</div>}
          </div>
        ) : (
          <p>部品を選択すると為替シミュレーションを実行できます。</p>
        )}
      </div>
    </>
  );

  const renderSettings = () => (
    <div className="content-card">
      <p className="section-label">Settings</p>
      <h2>設定</h2>
      <p>API接続先：{import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api"}</p>
      <p>CORSと外部APIキーはバックエンド環境変数で管理します。</p>
    </div>
  );

  const renderContent = () => {
    if (currentPage === "dashboard") return renderDashboard();
    if (currentPage === "detail") return renderDetail();
    if (currentPage === "parts") return renderParts();
    if (currentPage === "simulation") return renderSimulation();
    if (currentPage === "safety") return <SafetyStockAdmin />;
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
