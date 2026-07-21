# CMD-X サプライチェーン需要予測・在庫最適化

CMD-Xは、中部地区の中小部品メーカーが抱える「完成車メーカー内示の急変」「BOMをまたぐ部品影響の見落とし」「安全在庫の属人運用」を、需要予測・BOM展開・内示シミュレーション・動的安全在庫でつなぐ授業発表用プロトタイプです。画面モックではなく、ReactからFastAPIを呼び、CSV/SQLiteに保存されたデモデータを使って再読み込み後も状態を確認できます。

## 使用技術
- Backend: FastAPI, Pydantic, pandas, numpy, SQLite
- Forecast: Prophet 0.4 / XGBoost 0.6の説明に沿った時系列アンサンブル。デモ速度確保のため、製品予測と評価はトレンド/季節性/ラグ特徴の軽量実装です。
- Frontend: React, Vite, Chart.js
- Data: CSVマスタ、SQLite履歴

## 主な機能
- F-01: 工場、部品、製品アセンブリ選択。製品需要4週間予測とBOM構成部品別需要を表示。
- F-05: 完成車メーカー別の増減産内示シミュレーション。allocation_ratioを考慮し、製品と構成部品へ影響展開。結果はSQLiteへ履歴保存。
- F-08: RMSEとリードタイムから動的安全在庫を計算。プレビュー、マスタ更新、履歴保存、CLIバッチ、管理画面を提供。
- 既存機能: 部品需要予測、為替シミュレーション、JIT出荷ピーク予測を維持。

## 計算式
- 製品需要予測: 製品週次需要履歴を使い、トレンド/季節性をProphet相当、ラグ/ローリング特徴をXGBoost相当として、`Prophet 0.4 + XGBoost 0.6`で合成します。
- BOM必要数: `部品必要数 = 製品予測数 × quantity_per_product`
- メーカー内示:
  - 100%紐づき: `V_adjusted = round(V_next × (1 + r / 100))`
  - 配分あり: `V_adjusted = round(V_next × (1 - a) + V_next × a × (1 + r / 100))`
- 動的安全在庫:
  - `RMSE = sqrt(mean((actual_demand - predicted_demand)^2))`
  - `dynamic_safety_stock = ceil(safety_factor × RMSE × sqrt(lead_time_days / 7))`
  - 最小値、最大値、1回最大±50%、20%以上は要確認のガードレールを適用します。

## デモデータ
`python -m scripts.generate_demo_data`で再生成できます。
- 工場: F-01 名古屋第一工場、F-02 三河精密工場、F-03 豊田アセンブリ工場
- メーカー: 完成車A社、完成車B社、完成車C社（架空名称）
- 製品: PROD-A キャブレターASSY、PROD-B エンジン制御ASSY、PROD-C ブレーキ制御ASSY、PROD-D 冷却ユニットASSY
- 部品: 6部品以上、PT-1002とPT-5007などは複数製品で共通利用
- 履歴: 製品需要156週、部品需要156週、LT/予測精度12か月

## デモデータ再生成
プロジェクトルートから実行:

```bash
python -m scripts.generate_demo_data
```

検証も同時に実行:

```bash
python -m scripts.generate_demo_data --validate
```

## デモデータ検証
```bash
python -m scripts.validate_demo_data
```

検証では、必須CSV/カラム、ID参照整合性、負値、BOM必要数、JIT便比率と数量合計、代表KPI、完成車A社-20%内示、安全在庫の増加/減少、NaN/Infinity、同一生成の再現性を確認します。

## 推奨デモシナリオ
1. F-02 三河精密工場を選択
2. 製品アセンブリを選択
3. PROD-A キャブレターASSYを選択
4. 4週間需要予測を表示
5. 構成部品別表示へ切り替え
6. PT-1002の部品需要・生産推奨量・発注推奨量・出荷推奨量を確認
7. JIT出荷ピークで火曜10:00を確認
8. 完成車A社、-20%で内示シミュレーション
9. 通常予測と調整後予測を比較
10. 動的安全在庫プレビューで増加部品・減少部品を確認

## 想定される代表数値
`python -m scripts.generate_demo_data --validate`実行後の実データに基づく代表値です。

- 来週部品需要: 2,458個
- 現在庫: 1,800個
- 安全在庫: 540個
- 生産推奨量: 1,198個
- 発注推奨量: 1,198個
- 出荷推奨量: 2,458個
- JIT最大ピーク: 火曜10:00、233個
- 週間JIT合計: 2,458個
- 完成車A社-20%適用前: 1,229個
- 完成車A社-20%適用後: 983個
- 安全在庫変更前後: 540個 -> 270個

## 環境変数
実値をソースに入れないでください。`backend/.env.example`を参考に`backend/.env`を作成します。

```bash
FRED_API_KEY=
OPENWEATHER_API_KEY=
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CMDX_ENABLE_SCHEDULER=false
```

外部APIが使えない場合も、為替・PMI・気象はデモ用フォールバックで止まらない設計です。

## 起動方法
```bash
python -m scripts.generate_demo_data
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

別ターミナル:

```bash
cd cmdx-frontend
npm install
npm run dev
```

## テスト
```bash
cd backend
pytest

cd ../cmdx-frontend
npm run lint
npm run build
```

安全在庫バッチ:

```bash
cd backend
python -m scripts.update_dynamic_safety_stock --preview
python -m scripts.update_dynamic_safety_stock
```

## API一覧
- `GET /api/factories`
- `GET /api/parts`
- `GET /api/manufacturers`
- `GET /api/products`
- `GET /api/products?factory_id=F-02`
- `GET /api/products/{product_id}`
- `GET /api/products/{product_id}/bom`
- `GET /api/forecast`
- `GET /api/forecast/product`
- `POST /api/simulations/production-notice`
- `GET /api/simulations/production-notice/history`
- `DELETE /api/simulations/production-notice/history/{simulation_id}`
- `GET /api/safety-stock/settings`
- `PUT /api/safety-stock/settings`
- `GET /api/safety-stock/current`
- `GET /api/safety-stock/history`
- `GET /api/safety-stock/preview`
- `POST /api/safety-stock/optimize`
- `GET /api/shipment-peak`
- `GET /api/download/actual-history.csv`
- `GET /api/download/forecast.csv`
- `GET /api/download/future-actual-template.csv`

## データ管理・実績連携
「データ管理・実績連携」タブでは、現在バックエンドが利用しているCSVを画面から確認、出力、検証、反映できます。CSV更新時はバックアップを作成し、反映後に予測再計算と安全在庫再計算を選択できます。

対象13CSV:

- `factory_master.csv`
- `parts_master.csv`
- `product_master.csv`
- `bom_master.csv`
- `manufacturer_master.csv`
- `manufacturer_product_mapping.csv`
- `product_demand_history.csv`
- `internal_performance_history.csv`
- `jit_shipment_history.csv`
- `lead_time_history.csv`
- `forecast_accuracy_history.csv`
- `safety_stock_master.csv`
- `dynamic_safety_stock.csv`

主なAPI:

- `GET /api/data-management/summary`
- `GET /api/data-management/datasets`
- `GET /api/data-management/datasets/{dataset_id}/preview`
- `GET /api/data-management/datasets/{dataset_id}/download`
- `GET /api/data-management/export-all`
- `POST /api/data-management/import/validate`
- `POST /api/data-management/import/commit`
- `GET /api/data-management/backups`
- `POST /api/data-management/backups/{backup_id}/restore`
- `GET /api/data-management/forecast-export`
- `GET /api/data-management/future-actual-template`
- `POST /api/data-management/recalculate/forecast`
- `POST /api/data-management/recalculate/safety-stock`
- `POST /api/data-management/recalculate/all`
- `GET /api/data-management/weekly-update/settings`
- `PUT /api/data-management/weekly-update/settings`
- `POST /api/data-management/weekly-update/run-now`
- `GET /api/data-management/weekly-update/history`
- `POST /api/data-management/demo/next-week/preview`
- `POST /api/data-management/demo/next-week/commit`

CSVダウンロード:

1. 「データ管理・実績連携」タブを開く
2. データセット一覧の`DL`を押す
3. 現在バックエンドが利用しているCSVをUTF-8 BOM付きで出力

ZIPダウンロード:

1. 「全データ一括ZIP」を押す
2. 13CSVと`manifest.json`を含むZIPを取得

CSVアップロード:

1. 対象データセットを選択
2. 更新方式を選択
3. CSVファイルを選択
4. 「検証・プレビュー」を押す
5. エラーがなければ、必要な再計算を選んで「確定反映」

更新方式:

- 追記: 既存キーと重複しない行だけ追加
- 追記・上書き: 同一キーは更新し、新規キーは追加
- 全件置換: 対象CSVをすべて置換。バックアップ作成と確認チェックが必要

CSV検証内容:

- 必須カラム、未知カラム、空ファイル
- 主キー重複、完全重複行
- 日付、数値、負数、0禁止列
- ID参照整合性
- CSV数式インジェクション警告
- 極端な外れ値警告

バックアップ・復元:

- CSV反映、週次demo追加、復元前に`backend/data/backups/`へバックアップを作成
- 直近保持件数は`CMDX_BACKUP_RETENTION`で変更
- 画面のバックアップ一覧から復元可能

予測結果CSV:

- 「予測結果CSV」から出力
- 製品/部品/全対象の予測、在庫、安全在庫、推奨生産、推奨発注、推奨出荷を含む

将来実績入力テンプレート:

- 「将来実績テンプレート」から出力
- 予測済み未来週に実績を追記し、再アップロードに利用

実績取り込み後の再計算:

- データのみ反映
- 予測再計算
- 安全在庫再計算
- 予測と安全在庫の両方を再計算

自動週次更新:

- demo source: 現在CSVの最終実績週から次週を算出し、製品需要、部品実績、JIT、予測精度履歴を疑似生成
- directory source: 指定ディレクトリのCSVを検証し、成功時は`processed`へ、失敗時は`failed`へ移動
- 設定はSQLiteへ保存し、`.env`は初期値としてのみ利用

関連環境変数:

```bash
CMDX_BACKUP_RETENTION=10
CMDX_MAX_UPLOAD_MB=20
CMDX_ENABLE_WEEKLY_DATA_UPDATE=false
CMDX_WEEKLY_UPDATE_DAY=mon
CMDX_WEEKLY_UPDATE_HOUR=6
CMDX_WEEKLY_UPDATE_MINUTE=0
CMDX_WEEKLY_UPDATE_TIMEZONE=Asia/Tokyo
CMDX_WEEKLY_UPDATE_SOURCE=demo
CMDX_WEEKLY_UPDATE_DIRECTORY=
```

発表用データ管理デモ手順:

1. 「データ管理・実績連携」タブを開く
2. 現在のデータ期間、最終実績週、件数を説明
3. `product_demand_history.csv`をダウンロード
4. 将来実績入力テンプレートをダウンロード
5. サンプル実績CSVをアップロード
6. 検証結果と行別エラー/警告を表示
7. 追記・更新方式で反映
8. 最終実績週が更新されたことを確認
9. 予測と安全在庫を再計算
10. 既存ダッシュボードで予測値・推奨値がCSV更新後のデータから再計算されることを確認
11. 「最新週のデモ実績を生成」を実行
12. 自動更新設定と更新履歴を説明
13. バックアップ一覧と復元操作を説明

発表説明例:

「現在はデモデータを使用していますが、データ管理画面から企業が保有する実績CSVを取り込み、需要予測や生産・発注・出荷の推奨値へ反映できます。」

「また、現在の実績データや予測結果をCSVで出力し、確定実績を追記して再度取り込むことで、予測精度の評価や安全在庫の再計算に利用できます。」

「さらに、毎週の実績取得を想定した自動更新機能を備えており、実運用では基幹システムや生産管理システムとの連携へ拡張できます。」

## 5分デモ手順
1. ダッシュボードでF-02三河精密工場、製品アセンブリ、PROD-Aを選択。
2. 製品需要4週間予測を説明。
3. 「構成部品別」へ切り替え、BOMによる部品必要数を確認。
4. シミュレーション画面で完成車A社、PROD-A、-20%を実行。
5. 通常予測と内示調整後予測、部品別差分、処理時間を説明。
6. 安全在庫最適化画面でプレビューを実行。
7. RMSEとLTから新旧差分が出ることを説明。
8. 「今すぐ最適化」を実行。
9. ダッシュボードへ戻り、動的安全在庫と推奨発注に反映されたことを確認。

## 既知の制約
- 授業用デモデータは架空です。
- 製品予測はデモ速度を優先した軽量アンサンブルです。
- APSchedulerによる月次登録は`CMDX_ENABLE_SCHEDULER=true`で有効化します。開発時のreload二重実行を避けるため、デフォルトはCLI/API手動実行です。
- 警告はダッシュボード上に表示します。Slack/LINEなど外部通知は実装対象外です。
