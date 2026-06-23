import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend
);

function ShipmentPeakChart({ data = [], peakInfo }) {
  if (!data.length || !peakInfo) return null;

  const days = ["月", "火", "水", "木", "金", "土", "日"];
  const hours = ["06:30", "10:00", "15:30", "20:00"];

  const dayRows = days.map((day) => {
    const row = { day };

    hours.forEach((hour) => {
      const found = data.find(
        (item) =>
          item.day === day &&
          item.hour === hour
      );

      row[hour] = found ? found.volume : 0;
    });

    return row;
  });

  const colors = {
    "06:30": "rgba(59,130,246,0.8)",
    "10:00": "rgba(249,115,22,0.8)",
    "15:30": "rgba(34,197,94,0.8)",
    "20:00": "rgba(168,85,247,0.8)",
  };

  const chartData = {
    labels: days,
    datasets: hours.map((hour) => ({
      label: `${hour}便`,
      data: dayRows.map((row) => row[hour]),
      backgroundColor: colors[hour],
      borderColor: colors[hour],
      borderWidth: 1,
      stack: "shipment",
    })),
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,

    plugins: {
      legend: {
        position: "bottom",
      },

      tooltip: {
        callbacks: {
          label: (context) =>
            `${context.dataset.label}: ${Number(
              context.raw
            ).toLocaleString()}個`,
        },
      },
    },

    scales: {
      x: {
        stacked: true,
      },

      y: {
        stacked: true,
        beginAtZero: true,
        title: {
          display: true,
          text: "予測出荷量（個）",
        },
      },
    },
  };

  return (
    <div className="shipment-card">
      <div className="section-header">
        <div>
          <p className="section-label">
            F-07 JIT Peak Forecast
          </p>

          <h2>🚚 JIT出荷ピーク予測</h2>
        </div>

        <span className="badge">
          曜日・時間帯別
        </span>
      </div>

      <div className="peak-summary">
        <strong>
          ⚠️ 来週の出荷ピークは
          {" "}
          {peakInfo.day}曜日
          {" "}
          {peakInfo.hour}
          {" "}
          です
        </strong>

        <p>
          予測出荷量：
          {Number(
            peakInfo.volume
          ).toLocaleString()}
          個
        </p>

        <p>
          梱包人員の事前シフト確保、
          およびトラック配車調整を推奨します。
        </p>
      </div>

      <div
        style={{
          height: "450px",
          marginTop: "20px",
        }}
      >
        <Bar
          data={chartData}
          options={options}
        />
      </div>
    </div>
  );
}

export default ShipmentPeakChart;