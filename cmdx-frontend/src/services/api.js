const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

const handleResponse = async (response) => {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.error || "API通信でエラーが発生しました");
  }
  return data;
};

const get = async (path) => handleResponse(await fetch(`${API_BASE_URL}${path}`));

const send = async (path, method, payload) =>
  handleResponse(
    await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );

export const getFactories = () => get("/factories");
export const getParts = () => get("/parts");
export const getManufacturers = () => get("/manufacturers");
export const getProducts = (factoryId) => get(`/products${factoryId ? `?factory_id=${factoryId}` : ""}`);
export const getProductBom = (productId) => get(`/products/${productId}/bom`);
export const getSafetyStockSettings = () => get("/safety-stock/settings");
export const getSafetyStockCurrent = () => get("/safety-stock/current");
export const getSafetyStockHistory = () => get("/safety-stock/history");
export const previewSafetyStock = () => get("/safety-stock/preview");
export const optimizeSafetyStock = () => send("/safety-stock/optimize", "POST", {});
export const saveSafetyStockSettings = (settings) => send("/safety-stock/settings", "PUT", settings);
export const getProductionNoticeHistory = () => get("/simulations/production-notice/history");
export const getDataManagementSummary = () => get("/data-management/summary");
export const getDataManagementDatasets = () => get("/data-management/datasets");
export const getDataManagementPreview = (datasetId, limit = 20) => get(`/data-management/datasets/${datasetId}/preview?limit=${limit}`);
export const validateDataImport = (payload) => send("/data-management/import/validate", "POST", payload);
export const commitDataImport = (payload) => send("/data-management/import/commit", "POST", payload);
export const getDataBackups = () => get("/data-management/backups");
export const restoreDataBackup = (backupId) => send(`/data-management/backups/${backupId}/restore`, "POST", {});
export const previewDemoNextWeek = () => send("/data-management/demo/next-week/preview", "POST", {});
export const commitDemoNextWeek = (options) => {
  const params = new URLSearchParams({
    recalculate_forecast: String(options?.recalculateForecast ?? true),
    recalculate_safety_stock: String(options?.recalculateSafetyStock ?? true),
  });
  return send(`/data-management/demo/next-week/commit?${params.toString()}`, "POST", {});
};
export const recalculateDataForecast = () => send("/data-management/recalculate/forecast", "POST", {});
export const recalculateDataSafetyStock = () => send("/data-management/recalculate/safety-stock", "POST", {});
export const recalculateDataAll = () => send("/data-management/recalculate/all", "POST", {});
export const getWeeklyUpdateSettings = () => get("/data-management/weekly-update/settings");
export const saveWeeklyUpdateSettings = (settings) => send("/data-management/weekly-update/settings", "PUT", settings);
export const runWeeklyUpdateNow = () => send("/data-management/weekly-update/run-now", "POST", {});
export const getWeeklyUpdateHistory = () => get("/data-management/weekly-update/history");

const downloadCsv = (path, filename) => {
  const link = document.createElement("a");
  link.href = `${API_BASE_URL}${path}`;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
};

export const downloadActualHistoryCsv = ({ factoryId, targetType, targetId }) => {
  const params = new URLSearchParams();
  if (factoryId) params.set("factory_id", factoryId);
  if (targetType === "product") params.set("product_id", targetId);
  if (targetType === "part") params.set("parts_id", targetId);
  downloadCsv(`/download/actual-history.csv?${params.toString()}`, `cmdx_actual_history_${targetId}.csv`);
};

export const downloadForecastCsv = ({ factoryId, targetType, targetId }) => {
  const params = new URLSearchParams({
    factory_id: factoryId,
    target_type: targetType,
    target_id: targetId,
  });
  downloadCsv(`/download/forecast.csv?${params.toString()}`, `cmdx_forecast_${targetId}.csv`);
};

export const downloadFutureActualTemplateCsv = ({ factoryId, targetType, targetId }) => {
  const params = new URLSearchParams();
  if (factoryId) params.set("factory_id", factoryId);
  if (targetType === "product") params.set("product_id", targetId);
  if (targetType === "part") params.set("parts_id", targetId);
  downloadCsv(`/download/future-actual-template.csv?${params.toString()}`, `cmdx_future_actual_template_${targetId}.csv`);
};

export const downloadDatasetCsv = (datasetId) =>
  downloadCsv(`/data-management/datasets/${datasetId}/download`, `${datasetId}.csv`);

export const downloadAllDataZip = () =>
  downloadCsv("/data-management/export-all", "cmdx_data_export.zip");

export const downloadManagedForecastCsv = ({ factoryId, targetType, targetId } = {}) => {
  const params = new URLSearchParams();
  if (factoryId) params.set("factory_id", factoryId);
  if (targetType) params.set("target_type", targetType);
  if (targetId) params.set("target_id", targetId);
  downloadCsv(`/data-management/forecast-export?${params.toString()}`, "cmdx_forecast_export.csv");
};

export const downloadManagedFutureTemplate = ({ factoryId, targetType, targetId } = {}) => {
  const params = new URLSearchParams();
  if (factoryId) params.set("factory_id", factoryId);
  if (targetType === "product") params.set("product_id", targetId);
  if (targetType === "part") params.set("parts_id", targetId);
  downloadCsv(`/data-management/future-actual-template?${params.toString()}`, "cmdx_future_actual_template.csv");
};

export const getForecast = async (factoryId, partsId) => {
  if (!factoryId || !partsId) throw new Error("工場IDと部品IDを選択してください");
  const params = new URLSearchParams({ factory_id: factoryId, parts_id: partsId });
  return get(`/forecast?${params.toString()}`);
};

export const getProductForecast = async (factoryId, productId) => {
  if (!factoryId || !productId) throw new Error("工場IDと製品IDを選択してください");
  const params = new URLSearchParams({ factory_id: factoryId, product_id: productId });
  return get(`/forecast/product?${params.toString()}`);
};

export const runSimulation = async ({ factoryId, partsId, usdJpy }) => {
  const value = Number(usdJpy);
  if (Number.isNaN(value) || value <= 0 || value >= 500) {
    throw new Error("ドル円レートは0より大きく500未満で入力してください");
  }
  const data = await send("/simulate", "POST", {
    factory_id: factoryId,
    parts_id: partsId,
    usd_jpy: value,
  });
  const rate = Number(data.demand_change_rate);
  return {
    ...data,
    message:
      rate > 0
        ? `需要が${Math.abs(rate)}%増加すると予測されます`
        : rate < 0
          ? `需要が${Math.abs(rate)}%減少すると予測されます`
          : "需要変動はほとんどありません",
  };
};

export const runProductionNotice = ({ factoryId, manufacturerId, adjustmentRate, targetType, targetId }) => {
  const value = Number(adjustmentRate);
  if (Number.isNaN(value) || value < -50 || value > 50) {
    throw new Error("調整率は-50%〜+50%で入力してください");
  }
  return send("/simulations/production-notice", "POST", {
    factory_id: factoryId,
    manufacturer_id: manufacturerId,
    adjustment_rate: value,
    target_type: targetType || "product",
    target_id: targetId || null,
  });
};

export const getShipmentPeak = async (factoryId, partsId, nextWeekVolume) => {
  const params = new URLSearchParams({
    factory_id: factoryId,
    parts_id: partsId,
    next_week_volume: nextWeekVolume,
  });
  return get(`/shipment-peak?${params.toString()}`);
};

export const productForecast = async (productId, forecast) =>
  send("/product/forecast", "POST", { product_id: productId, forecast });
