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
