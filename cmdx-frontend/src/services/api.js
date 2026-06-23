const API_BASE_URL = "http://localhost:8000/api";

const handleResponse = async (response) => {
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || data.error || "API通信でエラーが発生しました");
  }

  return data;
};

export const getFactories = async () => {
  const response = await fetch(`${API_BASE_URL}/factories`);
  return handleResponse(response);
};

export const getParts = async () => {
  const response = await fetch(`${API_BASE_URL}/parts`);
  return handleResponse(response);
};

export const getForecast = async (factoryId, partsId) => {
  if (!factoryId || !partsId) {
    throw new Error("工場IDと部品IDを選択してください");
  }

  const params = new URLSearchParams({
    factory_id: factoryId,
    parts_id: partsId,
  });

  const response = await fetch(`${API_BASE_URL}/forecast?${params.toString()}`);
  return handleResponse(response);
};

export const runSimulation = async ({ factoryId, partsId, usdJpy }) => {
  const value = Number(usdJpy);

  if (Number.isNaN(value)) {
    throw new Error("ドル円レートは数値で入力してください");
  }

  if (value <= 0) {
    throw new Error("ドル円レートは0より大きい値を入力してください");
  }

  if (value >= 500) {
    throw new Error("ドル円レートの入力値が異常です");
  }

  const response = await fetch(`${API_BASE_URL}/simulate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      factory_id: factoryId,
      parts_id: partsId,
      usd_jpy: value,
    }),
  });

  const data = await handleResponse(response);

  const rate = Number(data.demand_change_rate);

  let message = data.message;

  if (rate > 0) {
    message = `需要が${Math.abs(rate)}%増加すると予測されます`;
  } else if (rate < 0) {
    message = `需要が${Math.abs(rate)}%減少すると予測されます`;
  } else {
    message = "需要変動はほとんどありません";
  }

  return {
    ...data,
    message,
  };
};

export const getShipmentPeak = async (
  factoryId,
  partsId,
  nextWeekVolume
) => {
  const response = await fetch(
    `http://localhost:8000/api/shipment-peak?factory_id=${factoryId}&parts_id=${partsId}&next_week_volume=${nextWeekVolume}`
  );

  if (!response.ok) {
    throw new Error("出荷ピーク予測取得失敗");
  }

  return response.json();
};