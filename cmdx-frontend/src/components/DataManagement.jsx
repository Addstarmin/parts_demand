import { useEffect, useMemo, useState } from "react";
import {
  commitDataImport,
  commitDemoNextWeek,
  downloadAllDataZip,
  downloadDatasetCsv,
  downloadManagedForecastCsv,
  downloadManagedFutureTemplate,
  getDataBackups,
  getDataManagementDatasets,
  getDataManagementPreview,
  getDataManagementSummary,
  getWeeklyUpdateHistory,
  getWeeklyUpdateSettings,
  previewDemoNextWeek,
  recalculateDataAll,
  recalculateDataForecast,
  recalculateDataSafetyStock,
  restoreDataBackup,
  runWeeklyUpdateNow,
  saveWeeklyUpdateSettings,
  validateDataImport,
} from "../services/api";

const fmt = (value) => (value === null || value === undefined || value === "" ? "―" : String(value));
const modeLabels = { append: "追記", upsert: "追記・上書き", replace: "全件置換" };
const categoryLabels = { master: "マスタデータ", history: "実績データ", ai: "AI・最適化データ" };

function DataPreviewTable({ rows }) {
  if (!rows?.length) return <div className="empty-state">表示できるプレビューがありません。</div>;
  const columns = Object.keys(rows[0]);
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>{columns.map((col) => <th key={col}>{col}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx}>
              {columns.map((col) => <td key={col}>{fmt(row[col])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DataManagement() {
  const [summary, setSummary] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [backups, setBackups] = useState([]);
  const [history, setHistory] = useState([]);
  const [settings, setSettings] = useState(null);
  const [preview, setPreview] = useState(null);
  const [uploadDataset, setUploadDataset] = useState("");
  const [uploadMode, setUploadMode] = useState("append");
  const [csvText, setCsvText] = useState("");
  const [originalFilename, setOriginalFilename] = useState("");
  const [validation, setValidation] = useState(null);
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const [recalcForecast, setRecalcForecast] = useState(true);
  const [recalcSafety, setRecalcSafety] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const groupedDatasets = useMemo(() => {
    const groups = { master: [], history: [], ai: [] };
    datasets.forEach((dataset) => groups[dataset.category]?.push(dataset));
    return groups;
  }, [datasets]);

  const refresh = async () => {
    const [summaryData, datasetData, backupData, settingsData, historyData] = await Promise.all([
      getDataManagementSummary(),
      getDataManagementDatasets(),
      getDataBackups(),
      getWeeklyUpdateSettings(),
      getWeeklyUpdateHistory(),
    ]);
    setSummary(summaryData);
    setDatasets(datasetData);
    setBackups(backupData);
    setSettings(settingsData);
    setHistory(historyData);
    setUploadDataset((prev) => prev || datasetData[0]?.dataset_id || "");
  };

  useEffect(() => {
    let active = true;
    window.setTimeout(() => {
      if (!active) return;
      refresh().catch((err) => {
        if (active) setError(err.message);
      });
    }, 0);
    return () => {
      active = false;
    };
  }, []);

  const runAction = async (action, successText) => {
    try {
      setLoading(true);
      setError("");
      setMessage("");
      const result = await action();
      setMessage(successText || result.message || "処理が完了しました。");
      await refresh();
      return result;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const handlePreviewDataset = async (datasetId) => {
    await runAction(async () => {
      const data = await getDataManagementPreview(datasetId, 20);
      setPreview(data);
      return data;
    }, "データプレビューを取得しました。");
  };

  const handleFile = async (event) => {
    const file = event.target.files?.[0];
    setValidation(null);
    setCsvText("");
    setOriginalFilename("");
    if (!file) return;
    const text = await file.text();
    setCsvText(text);
    setOriginalFilename(file.name);
  };

  const handleValidate = async () => {
    await runAction(async () => {
      const data = await validateDataImport({
        dataset_id: uploadDataset,
        update_mode: uploadMode,
        csv_text: csvText,
        original_filename: originalFilename || "upload.csv",
      });
      setValidation(data);
      return data;
    }, "CSV検証が完了しました。");
  };

  const handleCommit = async () => {
    await runAction(async () => {
      const data = await commitDataImport({
        session_id: validation.session_id,
        recalculate_forecast: recalcForecast,
        recalculate_safety_stock: recalcSafety,
        confirm_replace: replaceConfirmed,
      });
      setValidation(null);
      setCsvText("");
      return data;
    }, "CSVを反映しました。");
  };

  const handleSettingsSave = async () => {
    await runAction(() => saveWeeklyUpdateSettings(settings), "自動更新設定を保存しました。");
  };

  return (
    <>
      <div className="top-panel">
        <div>
          <p className="page-label">Data Management</p>
          <h1>データ管理・実績連携</h1>
          <p className="note">デモデータ・実績データ・予測結果を一元管理します。企業の実績CSVを取り込み、予測・推奨値・安全在庫へ反映できます。</p>
        </div>
      </div>

      {loading && <div className="info-message">処理中...</div>}
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      {summary && (
        <section className="kpi-grid">
          <div className="kpi-card"><p className="kpi-title">データ開始日</p><h2>{fmt(summary.data_start)}</h2><p className="kpi-sub">全CSVから算出</p></div>
          <div className="kpi-card"><p className="kpi-title">データ終了日</p><h2>{fmt(summary.data_end)}</h2><p className="kpi-sub">最終実績週: {fmt(summary.last_actual_week)}</p></div>
          <div className="kpi-card"><p className="kpi-title">実績件数</p><h2>{summary.performance_rows?.toLocaleString()}件</h2><p className="kpi-sub">JIT: {summary.jit_rows?.toLocaleString()}件</p></div>
          <div className="kpi-card"><p className="kpi-title">自動更新</p><h2>{summary.weekly_update_enabled ? "有効" : "無効"}</h2><p className="kpi-sub">次回: {fmt(summary.next_weekly_update_at)}</p></div>
        </section>
      )}

      <div className="content-card">
        <div className="section-header">
          <div>
            <p className="section-label">Operations</p>
            <h2>主要操作</h2>
          </div>
          <span className="badge">登録データセット {summary?.dataset_count || datasets.length}件</span>
        </div>
        <div className="button-row">
          <button onClick={downloadAllDataZip}>全データ一括ZIP</button>
          <button onClick={() => downloadManagedForecastCsv()}>予測結果CSV</button>
          <button onClick={() => downloadManagedFutureTemplate()}>将来実績テンプレート</button>
          <button onClick={() => runAction(previewDemoNextWeek, "最新週の生成プレビューを取得しました。").then((data) => data && setPreview({ dataset: { label: `次週生成 ${data.next_week}` }, rows: Object.values(data.datasets)[0]?.preview_rows || [] }))}>最新週のデモ実績を生成</button>
          <button onClick={() => runAction(() => commitDemoNextWeek({ recalculateForecast: true, recalculateSafetyStock: true }), "最新週のデモ実績を追加しました。")}>最新週を反映</button>
          <button onClick={() => runAction(recalculateDataForecast, "予測を再計算しました。")}>予測を再計算</button>
          <button onClick={() => runAction(recalculateDataSafetyStock, "動的安全在庫を再計算しました。")}>安全在庫を再計算</button>
          <button onClick={() => runAction(recalculateDataAll, "予測と安全在庫を再計算しました。")}>両方再計算</button>
        </div>
      </div>

      <div className="content-card">
        <div className="section-header">
          <div>
            <p className="section-label">Datasets</p>
            <h2>データセット一覧</h2>
          </div>
        </div>
        {Object.entries(groupedDatasets).map(([category, rows]) => (
          <div key={category}>
            <h3>{categoryLabels[category]}</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr><th>表示名</th><th>ファイル名</th><th>件数</th><th>開始</th><th>終了</th><th>最終更新</th><th>許可方式</th><th>操作</th></tr>
                </thead>
                <tbody>
                  {rows.map((dataset) => (
                    <tr key={dataset.dataset_id}>
                      <td>{dataset.label}</td>
                      <td>{dataset.filename}</td>
                      <td>{dataset.row_count.toLocaleString()}</td>
                      <td>{fmt(dataset.date_start)}</td>
                      <td>{fmt(dataset.date_end)}</td>
                      <td>{fmt(dataset.last_updated_at)}</td>
                      <td>{dataset.allowed_modes.map((m) => modeLabels[m]).join(" / ")}</td>
                      <td className="inline-actions">
                        <button onClick={() => downloadDatasetCsv(dataset.dataset_id)}>DL</button>
                        <button onClick={() => { setUploadDataset(dataset.dataset_id); setUploadMode(dataset.allowed_modes[0]); }}>選択</button>
                        <button onClick={() => handlePreviewDataset(dataset.dataset_id)}>確認</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>

      <div className="content-card">
        <div className="section-header">
          <div>
            <p className="section-label">CSV Import</p>
            <h2>CSVアップロード・検証・反映</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>対象データセット
            <select value={uploadDataset} onChange={(e) => { setUploadDataset(e.target.value); setValidation(null); }}>
              {datasets.map((dataset) => <option key={dataset.dataset_id} value={dataset.dataset_id}>{dataset.label}</option>)}
            </select>
          </label>
          <label>更新方式
            <select value={uploadMode} onChange={(e) => setUploadMode(e.target.value)}>
              {(datasets.find((d) => d.dataset_id === uploadDataset)?.allowed_modes || ["append"]).map((mode) => <option key={mode} value={mode}>{modeLabels[mode]}</option>)}
            </select>
          </label>
          <label>CSVファイル
            <input type="file" accept=".csv,text/csv" onChange={handleFile} />
          </label>
        </div>
        {uploadMode === "replace" && <p className="error-message">対象データをすべて置き換えます。既存データはバックアップされます。</p>}
        <div className="button-row">
          <button disabled={!csvText || loading} onClick={handleValidate}>検証・プレビュー</button>
        </div>
        {validation && (
          <div className="import-result">
            <div className="metric-grid">
              <div><span>追加</span><strong>{validation.added_rows}</strong></div>
              <div><span>更新</span><strong>{validation.updated_rows}</strong></div>
              <div><span>スキップ</span><strong>{validation.skipped_rows}</strong></div>
              <div><span>エラー</span><strong>{validation.error_count}</strong></div>
              <div><span>警告</span><strong>{validation.warning_count}</strong></div>
              <div><span>反映可否</span><strong>{validation.commit_allowed ? "可能" : "不可"}</strong></div>
            </div>
            {validation.errors?.length > 0 && <div className="error-message">{validation.errors.slice(0, 8).map((e) => <p key={`${e.row}-${e.message}`}>{e.row ? `${e.row}行目: ` : ""}{e.message}</p>)}</div>}
            {validation.warnings?.length > 0 && <div className="info-message">{validation.warnings.slice(0, 8).map((w) => <p key={`${w.row}-${w.message}`}>{w.row ? `${w.row}行目: ` : ""}{w.message}</p>)}</div>}
            <DataPreviewTable rows={validation.preview_rows} />
            <div className="form-grid">
              <label><span><input type="checkbox" checked={recalcForecast} onChange={(e) => setRecalcForecast(e.target.checked)} /> 反映後に予測再計算</span></label>
              <label><span><input type="checkbox" checked={recalcSafety} onChange={(e) => setRecalcSafety(e.target.checked)} /> 反映後に安全在庫再計算</span></label>
              {uploadMode === "replace" && <label><span><input type="checkbox" checked={replaceConfirmed} onChange={(e) => setReplaceConfirmed(e.target.checked)} /> 全件置換を確認しました</span></label>}
            </div>
            <button disabled={!validation.commit_allowed || loading || (uploadMode === "replace" && !replaceConfirmed)} onClick={handleCommit}>確定反映</button>
          </div>
        )}
      </div>

      {preview && (
        <div className="content-card">
          <div className="section-header">
            <div>
              <p className="section-label">Preview</p>
              <h2>{preview.dataset?.label || "データ確認"}</h2>
            </div>
          </div>
          <DataPreviewTable rows={preview.rows} />
        </div>
      )}

      <div className="content-card">
        <div className="section-header">
          <div>
            <p className="section-label">Weekly Update</p>
            <h2>自動更新設定</h2>
          </div>
        </div>
        {settings && (
          <>
            <div className="form-grid">
              <label>自動更新
                <select value={settings.enabled ? "true" : "false"} onChange={(e) => setSettings({ ...settings, enabled: e.target.value === "true" })}>
                  <option value="false">無効</option><option value="true">有効</option>
                </select>
              </label>
              <label>曜日
                <select value={settings.day} onChange={(e) => setSettings({ ...settings, day: e.target.value })}>
                  <option value="mon">月</option><option value="tue">火</option><option value="wed">水</option><option value="thu">木</option><option value="fri">金</option><option value="sat">土</option><option value="sun">日</option>
                </select>
              </label>
              <label>時<input type="number" value={settings.hour} onChange={(e) => setSettings({ ...settings, hour: Number(e.target.value) })} /></label>
              <label>分<input type="number" value={settings.minute} onChange={(e) => setSettings({ ...settings, minute: Number(e.target.value) })} /></label>
              <label>タイムゾーン<input value={settings.timezone} onChange={(e) => setSettings({ ...settings, timezone: e.target.value })} /></label>
              <label>更新ソース
                <select value={settings.source} onChange={(e) => setSettings({ ...settings, source: e.target.value })}>
                  <option value="demo">demo</option><option value="directory">directory</option>
                </select>
              </label>
              <label>directoryパス<input value={settings.directory || ""} onChange={(e) => setSettings({ ...settings, directory: e.target.value })} /></label>
              <label>再試行回数<input type="number" value={settings.retry_count} onChange={(e) => setSettings({ ...settings, retry_count: Number(e.target.value) })} /></label>
            </div>
            <p className="note">最終実行: {fmt(settings.last_run_at)} / 結果: {fmt(settings.last_result)} / 次回: {fmt(settings.next_run_at)}</p>
            <div className="button-row">
              <button onClick={handleSettingsSave}>設定を保存</button>
              <button onClick={() => runAction(runWeeklyUpdateNow, "週次更新を実行しました。")}>今すぐ実行</button>
            </div>
          </>
        )}
      </div>

      <div className="content-card">
        <div className="section-header"><div><p className="section-label">Backups</p><h2>バックアップ・復元</h2></div></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>ID</th><th>作成日時</th><th>契機</th><th>対象</th><th>操作</th></tr></thead>
            <tbody>
              {backups.slice(0, 10).map((backup) => (
                <tr key={backup.backup_id}>
                  <td>{backup.backup_id}</td><td>{backup.created_at}</td><td>{backup.trigger}</td><td>{backup.dataset_id || "all"}</td>
                  <td><button onClick={() => runAction(() => restoreDataBackup(backup.backup_id), "バックアップを復元しました。")}>復元</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="content-card">
        <div className="section-header"><div><p className="section-label">History</p><h2>更新履歴</h2></div></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>日時</th><th>種別</th><th>ソース</th><th>対象</th><th>状態</th><th>追加</th><th>更新</th><th>メッセージ</th></tr></thead>
            <tbody>
              {history.slice(0, 20).map((item) => (
                <tr key={item.update_id}>
                  <td>{item.executed_at}</td><td>{item.update_type}</td><td>{item.source}</td><td>{item.dataset_id || "―"}</td><td>{item.status}</td><td>{item.added_rows}</td><td>{item.updated_rows}</td><td>{item.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export default DataManagement;
