import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend
);

function ForecastChart({ chartData, title = "需要予測・在庫シミュレーション推移" }) {
  if (!chartData) return null;

  const labels = chartData.map((item) => item.date);

  const data = {
    labels,
    datasets: [
      {
        label: "過去実績（需要）",
        data: chartData.map((item) => item.actual),
        borderColor: "#64748b",      // 落ち着いたグレー
        backgroundColor: "transparent",
        borderWidth: 3,
        tension: 0.35,
        spanGaps: true,
      },
      {
        label: "通常予測",
        data: chartData.map((item) => item.normal_forecast ?? item.forecast),
        borderColor: "#2563eb",      // 鮮やかなブルー
        backgroundColor: "transparent",
        borderWidth: 3,
        tension: 0.35,
        spanGaps: true,
      },
      {
        label: "内示調整後予測",
        data: chartData.map((item) => item.adjusted_forecast),
        borderColor: "#f97316",
        backgroundColor: "transparent",
        borderWidth: 3,
        borderDash: [8, 5],
        tension: 0.35,
        spanGaps: true,
      },
      {
        label: "現在庫",
        data: chartData.map((item) => item.current_stock),
        borderColor: "#10b981",      // グリーン
        backgroundColor: "transparent",
        borderWidth: 2,
        borderDash: [4, 4],
        pointRadius: 2,
      },
      {
        label: "安全在庫閾値",
        data: chartData.map((item) => item.safety_stock),
        borderColor: "#ef4444",      // 警告のレッド
        backgroundColor: "transparent",
        borderWidth: 2,
        borderDash: [6, 6],
        pointRadius: 0,
      },
    ],
  };

  const options = {
    responsive: true,
    plugins: {
      legend: {
        position: "bottom",
      },
      tooltip: {
        callbacks: {
          label: (context) => {
            const value = context.raw;
            if (value === null || value === undefined) return `${context.dataset.label}: データなし`;
            return `${context.dataset.label}: ${Number(value).toLocaleString()}個`;
          },
          afterBody: (items) => {
            const item = chartData[items[0].dataIndex];
            if (item?.difference === null || item?.difference === undefined) return "";
            return `差分: ${Number(item.difference).toLocaleString()}個`;
          },
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        title: { display: true, text: "数量（個）" },
      },
      x: { title: { display: true, text: "週" } },
    },
  };

  return (
    <div className="chart-card">
      <div className="section-header">
        <div>
          <p className="section-label">Forecast</p>
          <h2>{title}</h2>
        </div>
        <span className="badge">AI予測モデル連動</span>
      </div>

      {chartData.length > 0 ? (
        <Line data={data} options={options} />
      ) : (
        <p>グラフデータがありません。</p>
      )}
    </div>
  );
}

export default ForecastChart;
