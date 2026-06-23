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

function ForecastChart({ chartData = [] }) {
  const labels = chartData.map((item) => item.date);

  const data = {
    labels,
    datasets: [
      {
        label: "過去実績",
        data: chartData.map((item) => item.actual),
        borderWidth: 3,
        tension: 0.35,
        spanGaps: true,
      },
      {
        label: "AI需要予測",
        data: chartData.map((item) => item.forecast),
        borderWidth: 3,
        tension: 0.35,
        spanGaps: true,
      },
      {
        label: "現在庫",
        data: chartData.map((item) => item.current_stock),
        borderWidth: 2,
        borderDash: [4, 4],
        pointRadius: 0,
      },
      {
        label: "安全在庫",
        data: chartData.map((item) => item.safety_stock),
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
            if (value === null || value === undefined) {
              return `${context.dataset.label}: データなし`;
            }
            return `${context.dataset.label}: ${Number(value).toLocaleString()}個`;
          },
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
      },
    },
  };

  return (
    <div className="chart-card">
      <div className="section-header">
        <div>
          <p className="section-label">Forecast</p>
          <h2>需要予測推移</h2>
        </div>
        <span className="badge">API連携</span>
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