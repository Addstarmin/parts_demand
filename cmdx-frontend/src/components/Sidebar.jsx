import { FiBarChart2, FiBox, FiCpu, FiDatabase, FiHome, FiSettings, FiShield } from "react-icons/fi";

function Sidebar({ currentPage, setCurrentPage }) {
  const menuItems = [
    {
      id: "dashboard",
      label: "ダッシュボード",
      icon: <FiHome />,
    },
    {
      id: "detail",
      label: "詳細分析",
      icon: <FiBarChart2 />,
    },
    {
      id: "parts",
      label: "部品情報",
      icon: <FiBox />,
    },
    {
      id: "simulation",
      label: "シミュレーション",
      icon: <FiCpu />,
    },
    {
      id: "safety",
      label: "安全在庫最適化",
      icon: <FiShield />,
    },
    {
      id: "data",
      label: "データ管理・実績連携",
      icon: <FiDatabase />,
    },
    {
      id: "settings",
      label: "設定",
      icon: <FiSettings />,
    },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">C</div>
        <div>
          <h1>CMD-X</h1>
          <p>Manufacturing DX</p>
        </div>
      </div>

      <nav className="sidebar-menu">
        {menuItems.map((item) => (
          <button
            key={item.id}
            className={
              currentPage === item.id
                ? "sidebar-item active"
                : "sidebar-item"
            }
            onClick={() => setCurrentPage(item.id)}
          >
            <span className="sidebar-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-user">
        <div className="user-avatar">T</div>
        <div>
          <p className="user-name">Test</p>
          <p className="user-role">調達担当者</p>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
