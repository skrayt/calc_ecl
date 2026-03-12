# ECL将来予想モデル 実装計画

## 概要

IFRS9/ECLモデルの将来予想に必要な統計分析機能をFlet GUIアプリとして実装する。

**本番環境: WinPython64-3.12.4.1（オフライン）**

---

## 進捗状況

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 1 | 基盤更新 | **完了** |
| Phase 2 | 分析ロジック（data_transform / correlation / regression / model_selection / arima） | **完了** |
| Phase 3 | Flet GUIアプリ構築（タブ①〜⑦） | **完了** |
| Phase 4 | ドキュメント更新 | **完了** |
| **Phase 6A** | **バグ修正・緊急改善** | **完了** |
| **Phase 6B** | **UI統一（説明変数選択欄の全ページ統一）** | **完了** |
| **Phase 6C** | **変数別変換・ラグ設定の統合（設計変更）** | **完了** |
| **Phase 6D** | **データ閲覧拡張（比較プロット・インポート改善）** | **完了（①②のみ。③インポートモード選択は後回し）** |
| **Phase 6E** | **ARIMA改善** | **完了（E-1のみ。E-2はPhase 5-6で対応）** |
| **Phase 6F** | **解釈説明・マニュアル充実** | **完了** |
| Phase 5-1 | DB拡張（ECL計算用テーブル） | **完了** |
| Phase 5-2 | src/analysis/ecl.py（ECL計算コアロジック） | **完了** |
| Phase 5-3 | src/db_operations.py 拡張 | **完了** |
| Phase 5-4 | page_arima.py 拡張（予測結果の保存機能） | **完了** |
| Phase 5-5 | page_model_confirm.py（⑦モデル確定タブ） | **完了** |
| Phase 5-6 | page_ecl.py（⑧ECL計算タブ） | **完了** |
| Phase 5-7 | ドキュメント更新（Phase 5完了後） | **完了** |
| **Phase 7A** | **バグ修正（ECL Timestamp・重複保存防止）** | **完了** |
| **Phase 7B** | **年次管理（ARIMA/モデル確定の決算年月紐付け・一覧改善）** | **完了** |
| **Phase 7C** | **reference_date 期末化（CSVインポート・マイグレーションSQL）** | **完了** |
| **Phase 7D** | **データ閲覧改善（標準化スイッチ・比較プロット右軸選択）** | **完了** |
| **Phase 7E** | **回帰VIF列追加・動的回帰標準化トグル無効化** | **完了** |
| **Phase 7F** | **ARIMA/ECL一覧改善・ECL詳細表示・決算年月自動設定** | **完了** |
| **Phase W1** | **DB接続二重化（環境変数フォールバック）** | **完了** |
| **Phase W2** | **main.py Web/デスクトップ切替** | **完了** |
| **Phase W3** | **Supabase DBセットアップ（手動作業）** | **完了** |
| **Phase W4** | **Renderデプロイ設定・デプロイ成功** | **完了** |
| **Phase W4b** | **Renderから Google Cloud Run へ移行（EdgeブラウザのSSL問題回避）** | **完了** |
| **Phase W5** | **FilePickerのWeb対応** | **未着手** |
| **Phase W6** | **ドキュメント更新（Web公開対応）** | **未着手** |

**実装順序: Phase 6A → 6B → 6C → 6D → 6E → 6F → Phase 5 → Phase 7A → 7B → 7C → 7D → 7E → 7F → Phase W1 → W2 → W3 → W4 → W4b → W5 → W6**

### Phase W4b: Google Cloud Run 移行（2026-03-12）

**背景:** RenderデプロイはMacのBrave/Chrome/Safariからは正常アクセスできたが、
WindowsのEdgeブラウザ（会社PC・モバイルルーター双方）で証明書エラーが発生。
`onrender.com` ドメインがEdgeのSmartScreenにより遮断されていたと推定。

**対応:** Google Cloud Run（`*.run.app` ドメイン）に移行。

**公開URL:** https://calc-ecl-610737115709.asia-northeast1.run.app

**構成:**
- ホスティング: Google Cloud Run（asia-northeast1リージョン、無料枠）
- DB: Supabase（変更なし）
- Dockerfile新規作成（python:3.12-slim + fonts-noto-cjk）
- 環境変数: Cloud Runコンソールで設定（DATABASE_URL / DB_SCHEMA / DB_SSLMODE / FLET_WEB）

**スクリーンショット:**
- `25_cloudrun_deploy_confirm.png` — Cloud Shellでのデプロイ実行（認証確認）
- `26_cloudrun_deploy_success.png` — デプロイ成功・Service URL発行
- `27_cloudrun_db_error.png` — 初回アクセス時のDB接続エラー（環境変数未設定）
- `28_cloudrun_env_check.png` — Cloud Shellでの環境変数確認
- `29_cloudrun_env_set_success.png` — Cloud ConsoleでのGUI環境変数設定・再デプロイ成功

---

## 残タスク・動作確認事項（2026-03-10 時点）

Phase 5-1〜5-7まで実装完了。以下は未実施の動作確認と今後の課題。

### 動作確認（E2Eテスト）

| 確認項目 | 状態 | 備考 |
|---------|------|------|
| DB migration: 004_create_ecl_tables.sql の実行 | **完了** | PgAdmin4で実行済み |
| DB migration: 005_update_reference_date_to_period_end.sql の実行 | **完了** | 既存データのreference_date期末化済み |
| ⑧ モデル確定タブ: 起動・回帰実行・DB保存の動作確認 | **完了** | |
| ⑥ ARIMAタブ: 予測保存ボタンの動作確認 | **完了** | 2件保存確認 |
| ⑨ ECL計算タブ: E2Eフロー（モデル選択 → ARIMA割当 → 計算 → CSV出力） | **完了** | ECL計算・DB保存・CSVエクスポート確認 |
| model_configs.hyperparameters に feature_stats が正しく保存されるか確認 | **未実施** | 標準化ON時の逆変換の正確性に影響 |

### 既知の設計上の制限・改善候補（Phase 7対応予定）

| 項目 | 内容 | 優先度 |
|------|------|--------|
| シナリオ方向設定 | 変数によって lower/upper が楽観/悲観の対応が逆になる（失業率 vs GDP等） | 中 |
| DataSourceSelector 内部属性アクセス | プライベート属性を直接参照している。公開プロパティ追加が望ましい | 低 |
| Phase 6D-③ | 目的変数の一括インポートGUI（インポートモード選択）が未実装 | 低 |

---

## Phase 7: 第2次レビュー対応（2026-03-11 追加）

### 7A: バグ修正・重複防止 【完了】

| # | 対象 | 問題 | 状態 |
|---|------|------|------|
| 7A-1 | `pages/page_ecl.py` | `Timestamp` object has no `__getitem__`エラー → `str(r['created_at'])[:10]`で修正 | **完了** |
| 7A-2 | `pages/page_model_confirm.py` | 重複保存防止: 同名モデルチェック + 保存後ボタン無効化 | **完了** |

---

### 7B: 年次管理の整備 【完了】

| # | 対象 | 変更内容 | 状態 |
|---|------|---------|------|
| 7B-1 | `pages/page_arima.py` | 決算年月ラベル表示 + 保存済み予測一覧（削除ボタン付き） | **完了** |
| 7B-2 | `pages/page_arima.py` | 同一dataset_idの重複ARIMA → 上書き確認ダイアログ | **完了** |
| 7B-3 | `pages/page_model_confirm.py` | `hyperparameters` JSONBに `fiscal_year_month` を記録 | **完了** |
| 7B-4 | `pages/page_model_confirm.py` | 保存済みモデル一覧のID列 → 決算年月列に変更 | **完了** |

---

### 7C: reference_date 期末化 【完了】

#### 設計変更内容

`reference_date` の格納規則を**期初→期末**に変更する。

| frequency | 変更前（期初） | 変更後（期末） |
|-----------|-------------|-------------|
| monthly | `2025-01-01` | `2025-01-31` |
| quarterly | `2025-01-01` (Q1) | `2025-03-31` |
| calendar_year | `2025-01-01` | `2025-12-31` |
| fiscal_year | `2025-04-01` | `2026-03-31` |

**各タブでのデータ取得は `WHERE frequency = %s` のまま変更なし**。load_indicators は指定frequencyのデータのみ返す（frequency変換・包含ロジックは不採用）。

#### 対応ファイル

| ファイル | 変更内容 |
|---------|---------|
| `CLAUDE.md` | reference_date のルールを期末に改訂 |
| `src/import_indicators.py` | `parse_time_point()` の期末変換ロジックに変更 |
| `src/import_targets.py` | 同上 |
| `db/migrations/005_update_reference_date_to_period_end.sql` | 既存データをUPDATEするSQL（実行済み）|

#### 既存データ移行SQL（005）

```sql
-- monthly: 月末日に更新
UPDATE indicator_data
SET reference_date = (DATE_TRUNC('month', reference_date) + INTERVAL '1 month' - INTERVAL '1 day')::DATE
WHERE frequency = 'monthly';

-- quarterly: 四半期末に更新（1月→3月末、4月→6月末、7月→9月末、10月→12月末）
UPDATE indicator_data
SET reference_date = (DATE_TRUNC('month', reference_date) + INTERVAL '3 months' - INTERVAL '1 day')::DATE
WHERE frequency = 'quarterly';

-- calendar_year: 12月31日に更新
UPDATE indicator_data
SET reference_date = (DATE_TRUNC('year', reference_date) + INTERVAL '1 year' - INTERVAL '1 day')::DATE
WHERE frequency = 'calendar_year';

-- fiscal_year: 翌年3月31日に更新（4月1日 → 翌3月31日）
UPDATE indicator_data
SET reference_date = (DATE_TRUNC('year', reference_date + INTERVAL '9 months') + INTERVAL '1 year' + INTERVAL '2 months' + INTERVAL '30 days')::DATE
WHERE frequency = 'fiscal_year';

-- target_dataも同様
UPDATE target_data SET reference_date = (DATE_TRUNC('month', reference_date) + INTERVAL '1 month' - INTERVAL '1 day')::DATE WHERE frequency = 'monthly';
UPDATE target_data SET reference_date = (DATE_TRUNC('month', reference_date) + INTERVAL '3 months' - INTERVAL '1 day')::DATE WHERE frequency = 'quarterly';
UPDATE target_data SET reference_date = (DATE_TRUNC('year', reference_date) + INTERVAL '1 year' - INTERVAL '1 day')::DATE WHERE frequency = 'calendar_year';
UPDATE target_data SET reference_date = (DATE_TRUNC('year', reference_date + INTERVAL '9 months') + INTERVAL '1 year' + INTERVAL '2 months' + INTERVAL '30 days')::DATE WHERE frequency = 'fiscal_year';
```

---

### 7D: データ閲覧ページ改善 【完了】

| # | 変更内容 | 状態 |
|---|---------|------|
| 7D-1 | 説明変数・目的変数タブに**標準化スイッチ（z-score）**を追加。[0,1]範囲変数は自動スキップ | **完了** |
| 7D-2 | 比較プロットの figsize を `(14,5)` → `(12,6)`（DEFAULT_FIGSIZE）に統一 | **完了** |
| 7D-3 | 比較プロット: `dual_axis`トグル廃止 → **「右軸に割り当てる変数」チェックボックス**方式に変更 | **完了** |
| 7D-4 | 「0-1正規化」表記はmin-max normalizationとして正しいため変更なし | **完了（変更なし）** |

**変更ファイル**: `components/plot_utils.py`（`plot_compare_series`のシグネチャ変更）、`pages/page_data_view.py`

---

### 7E: 分析ページ改善 【完了】

| # | 対象 | 変更内容 | 状態 |
|---|------|---------|------|
| 7E-1 | `pages/page_regression.py` | 係数テーブルに **VIF列**を追加（`calc_vif(X)` の結果を紐付け。VIF>10赤・VIF>5オレンジ） | **完了** |
| 7E-2 | `pages/page_dynamic_regression.py`, `components/variable_selector.py` | 変数ロード後に各変数の値が `[0,1]` 範囲内か判定。該当変数の標準化トグルを無効化（グレーアウト） | **完了** |

**7E-2 の判定ロジック**:
```python
# 変数ごとに標準化可否を判定
def is_unit_range(series: pd.Series) -> bool:
    """全値が[0,1]範囲に収まる場合True（標準化不要変数の検出）"""
    clean = series.dropna()
    return bool(len(clean) > 0 and (clean >= 0).all() and (clean <= 1).all())
```

---

### 7F: ARIMA/ECL一覧改善・ECL詳細表示・決算年月自動設定 【完了】

| # | 対象 | 変更内容 |
|---|------|---------|
| 7F-1 | `pages/page_data_view.py` | データ読込時に `dataset_id` / `frequency` をセッションに保存 |
| 7F-2 | `pages/page_arima.py` | 保存済みARIMA一覧をページ初期表示時に表示（予測実行前でも表示） |
| 7F-3 | `pages/page_arima.py` | 一覧フィルタを「この変数のみ」→「このデータセットの全変数」に変更。変数名列を追加 |
| 7F-4 | `src/db_operations.py` | `load_arima_forecasts()` に `dataset_id` フィルタ引数を追加 |
| 7F-5 | `pages/page_ecl.py` | CSVエクスポートを `page.set_clipboard()` → `subprocess pbcopy/clip` に変更（Flet 0.81.0対応） |
| 7F-6 | `pages/page_ecl.py` | 保存済みECL一覧を常時表示。決算年月ドロップダウンでフィルタ |
| 7F-7 | `pages/page_ecl.py` | ECL一覧に「詳細表示」ボタン（ダイアログで結果テーブルを表示） |
| 7F-8 | `pages/page_ecl.py` | ECL保存時の `fiscal_year_month` をモデルの `dataset_id` → `indicator_datasets` から自動取得 |
| 7F-9 | `src/db_operations.py` | `load_ecl_results()` に `fiscal_year_month` フィルタ追加。`list_ecl_fiscal_year_months()` / `delete_ecl_result()` / `load_ecl_result_detail()` を追加 |
| 7F-10 | `src/db_operations.py` | `load_model_result()` に `dataset_id` カラムを追加 |

---

### Phase 7 実装順序

```
Phase 7A（バグ修正）               ← 最優先
        ↓
Phase 7B（年次管理）               ← 7A完了後
        ↓
Phase 7C（reference_date期末化）   ← DB手動実行が必要。設計変更として最重要
        ↓
Phase 7D（データ閲覧改善）         ← 7C完了後（frequency包含ロジックを前提とする）
        ↓
Phase 7E（分析ページ改善）         ← 7D完了後または並行可

---

## レビューフィードバック整理（2026-03-10 テスト結果）

### フィードバック原文のページ別分類

| ページ | 番号 | 内容 | 分類 |
|--------|------|------|------|
| データ閲覧 | 1 | データ変換機能が欲しい | 新機能（6D） |
| データ閲覧 | 2 | 説明変数と目的変数を同じ画面でプロット（新タブ） | 新機能（6D） |
| データ閲覧 | 3 | 選択した変数を1グラフで重ねて表示する機能 | 新機能（6D） |
| データ閲覧 | 4 | 目的変数インポートはレコード追加方式・初回一括インポートGUI | 設計確認→新機能（6D） |
| データ閲覧 | 5 | 目的変数タブのデータセット名・タイプ・単位フィールドは機能しているか | バグ確認（6A） |
| データ閲覧 | 6 | セグメント情報は絞り込みに使っているか | 仕様確認（6A） |
| 相関分析 | 1 | 説明変数選択欄が旧式のまま | UI統一（6B） |
| 相関分析 | 2 | データ変換が一括のみ（動的回帰と異なる）。仕様通り？ | 設計決定（6C） |
| 相関分析 | 3 | 相関分析の追加プロット・指標はないか | 機能拡張（後回し） |
| 回帰分析 | 1 | 説明変数選択欄が旧式のまま | UI統一（6B） |
| 回帰分析 | 2 | データ変換が一括のみ。仕様通り？ | 設計決定（6C） |
| 回帰分析 | 3 | 交差検証の分割数の説明が欲しい | ヘルプ充実（6F） |
| 回帰分析 | 4 | ラグは一律のみ。変数ごとに異なるラグは想定されないか | 設計決定（6C） |
| 回帰分析 | 5 | 交差検証結果・残差プロットの解釈説明を充実させてほしい | ヘルプ充実（6F） |
| 回帰分析 | 6 | 残差ヒストグラムを「時系列残差プロット」と説明している | バグ（6A） |
| 回帰分析 | 7 | MSE標準偏差・各foldのMSEが画面に見えない | バグ→表示追加（6A） |
| モデル選択 | 1 | 説明変数選択欄が旧式のまま | UI統一（6B） |
| モデル選択 | 2 | データ変換が一括のみ。仕様通り？ | 設計決定（6C） |
| モデル選択 | 3 | 評価結果のfeaturesを日本語・改行表示にしてほしい | UI改善（6B） |
| モデル選択 | 4 | 優位な値に色付けは可能か | UI改善（6B） |
| モデル選択 | 5 | ラグは一律のみ。変数ごとのラグは想定されないか | 設計決定（6C） |
| モデル選択 | 6 | VIF<=10フィルタのトグルが機能しない（全数/全数のまま） | バグ（6A） |
| 動的回帰 | 1 | 各ページで変数別設定できればこのページは不要では？ | 設計見直し（6C） |
| 動的回帰 | 2 | 説明変数は変換・標準化できるが目的変数はできない。混在した結果に意味は？ | 設計確認（6C） |
| ARIMA | 1 | nlagsデフォルト20がデータ数40未満では使えない。自由入力フィールドが欲しい | バグ（6A） |
| ARIMA | 2 | 将来シナリオで手動入力値を優先、なければARIMA予測値を採用する方式に | 新機能（6E） |
| ARIMA | 3 | 実務担当者向けのARIMA解説・マニュアルを充実させてほしい | ドキュメント（6F） |

---

## Phase 6A: バグ修正・緊急改善 【完了 2026-03-10 commit: 5263cc9】

### 修正項目一覧

| # | 対象ファイル | 問題 | 修正内容 | 状態 |
|---|-----------|------|---------|------|
| A-1 | `components/plot_utils.py` | マニュアル記載の「時系列残差プロット」がGUIに存在しなかった | `plot_residuals` を3プロット構成に変更（左: 残差vs予測値 / 中: **時系列残差プロット** / 右: 残差ヒストグラム） | **完了** |
| A-1 | `pages/page_regression.py` | セクション見出し「残差プロット」が内容を示さない | 見出しを「残差プロット（左: 残差vs予測値 ／ 中: 時系列残差 ／ 右: 残差ヒストグラム）」に更新 | **完了** |
| A-2 | `pages/page_regression.py` | 各fold MSE・標準偏差が非表示 | fold別MSEテーブルと解釈注釈を追加 | **完了** |
| A-3 | `pages/page_model_selection.py` | VIFフィルタがDW条件も誤適用（デフォルト引数の罠） | `filter_models(min_dw=None, max_dw=None)` で修正 | **完了** |
| A-3 | `pages/page_model_selection.py` | 分析後にprogress_textが「全数/全数」のまま残留 | 分析完了後に `progress_text.value = ""` でクリア | **完了** |
| A-3 | `pages/page_model_selection.py` | トグル切替後に再実行しないとフィルタが反映されない | `on_vif_toggle` ハンドラを追加し即時再フィルタリング | **完了** |
| A-3 | `pages/page_model_selection.py` | features列が英語コードのみ・一行表示 | 日本語変数名・改行表示に変更。Adj.R²・max_VIF・F p値に色付け | **完了** |
| A-4 | `pages/page_arima.py` | nlags固定値20がデータ数40未満で失敗 | UIにnlags入力フィールドを追加（空欄でデータ数÷3の自動算出） | **完了** |
| A-5/A-6 | `pages/page_data_view.py` | 目的変数タブのフィールド機能確認・セグメント利用確認 | **未着手**（6D拡張と同時に対応予定） | 保留 |

---

## Phase 6B: UI統一（全ページ共通化）

**目的:** ②相関分析・③回帰分析・④モデル選択の説明変数選択欄を、⑤動的回帰と同じ新式UI（DataSourceSelector）に統一する。

### 修正対象

| ページ | 現状 | 修正後 |
|--------|------|--------|
| `page_correlation.py` | 旧式チェックボックス | DataSourceSelector + VariableSelector |
| `page_regression.py` | 旧式チェックボックス | DataSourceSelector + VariableSelector |
| `page_model_selection.py` | 旧式チェックボックス | DataSourceSelector + VariableSelector |

### モデル選択ページのUI改善

| 改善項目 | 内容 |
|---------|------|
| features列の日本語表示 | code_to_nameマッピングを使い、変数名を日本語で表示。複数変数は改行で区切る |
| 有意な値の色付け | p値<0.05の変数を緑、VIF>10の変数を赤でハイライト。Adj.R²・AIC等も相対比較で色付け |

---

## Phase 6C: 変数別変換・ラグ設定の統合方針（設計変更）

### 基本方針（レビューを踏まえた設計変更）

**動的回帰ページの役割を「変数別設定専用タブ」として明確化し、他ページへのトグル追加は行わない。**

理由:
- 変数別設定は組み合わせが爆発的に増加し、モデル選択（組み合わせ探索）との相性が悪い
- 相関分析・モデル探索は「一括変換で全体傾向を把握」する用途なので一括変換が適切
- 動的回帰ページで変数別設定を行った後、回帰分析ページで精査するワークフローが合理的

### 各ページの変換方式（確定）

| ページ | 変換方式 | 理由 |
|--------|---------|------|
| ②相関分析 | 一括（全変数同じ変換） | 全変数の相関関係を均等に比較するため |
| ③回帰分析 | 一括 | まず全変数同じ条件で評価する段階 |
| ④モデル選択 | 一括 | 全組み合わせ探索は一括変換が前提（変数別にすると組み合わせ数が爆発） |
| ⑤動的回帰 | **変数別（現状維持）** | 変数ごとの細かな設定はここで行う |

### 目的変数の変換・標準化方針

**目的変数（PD/LGD）は変換・標準化しない。**

理由:
- PD/LGDは解釈可能な率（0〜1）であり、変換すると実務解釈が困難になる
- 標準化した目的変数と非標準化の説明変数を混在させた場合、係数の解釈が困難
- 必要であれば説明変数側の標準化で対応する

→ 動的回帰ページに「目的変数は変換・標準化の対象外」という注意書きを追加する。

### ラグ設定方針

| ページ | ラグ設定 | 理由 |
|--------|---------|------|
| ②③④ | 一律（全変数に同じラグ） | 探索段階では一律が効率的 |
| ⑤動的回帰 | **変数別（現状維持）** | 細かな調整はここで行う |

モデル選択ページで「変数ごとにラグが異なるパターン」を探索したい場合は、動的回帰ページで個別設定した上でモデル確定タブに直接保存する運用で対応。

---

## Phase 6D: データ閲覧ページ拡張 【完了（新機能①②）2026-03-10】

**対象ファイル:** `pages/page_data_view.py`

### 新機能①: データ変換後プロット（既存タブに追加）

既存の説明変数タブ・目的変数タブに「変換してプロット」機能を追加。

```
変換方法: [none / log / diff / log_diff / arcsinh / arcsinh_diff ▼]
[変換してプロット]
```

### 新機能②: 比較プロット（新タブ「③ 比較プロット」）

説明変数・目的変数を横断的に選択し、1つのグラフで重ねて表示する。

**UI構成:**
```
────────────────────────────────────────
 データソース選択（DataSourceSelector）
────────────────────────────────────────
 変数選択（説明変数・目的変数を横断選択可）
  □ unemployment_rate（完全失業率）
  □ gdp_growth（実質GDP成長率）
  □ pd_corporate（コーポレートPD）
  ※ 最大8変数まで同時選択可
────────────────────────────────────────
 表示オプション
  ○ 2軸表示（左軸: 説明変数、右軸: 目的変数）
  ○ 正規化表示（各系列を0-1スケールに正規化して比較）
────────────────────────────────────────
 [プロット表示]
────────────────────────────────────────
```

### 新機能③: 目的変数の一括インポートGUI

現在は目的変数のインポートがレコード追加方式のみ。初回は複数年分を一括インポートできる機能を追加。

**運用フロー:**
- 初回: 「一括インポート」ボタン → CSVの全レコードを一括登録
- 毎年: 「レコード追加」ボタン → 最新年のデータのみ追加（既存データを上書きしない）

**UI追加箇所:** 目的変数タブのインポートセクションに「インポートモード」を選択するラジオボタンを追加。

---

## Phase 6E: ARIMA改善

**対象ファイル:** `pages/page_arima.py`, `pages/page_forecast.py`

### E-1: ADF検定のnlags改善

| 変更前 | 変更後 |
|--------|--------|
| デフォルト値=20（データ数40未満で使用不可） | デフォルト値なし（statsmodelsが自動選択）＋任意入力フィールドを追加 |

```python
# 変更前
result = adfuller(series, maxlag=20)

# 変更後（nlags入力フィールドが空の場合はNone=自動）
nlags = int(nlags_field.value) if nlags_field.value else None
result = adfuller(series, maxlag=nlags)
```

**UIに追加:**
```
ADF検定 nlagsオプション: [    ] （空欄で自動選択）
ℹ️ データ数の1/3以下を目安に設定。空欄の場合はstatsmodelsが自動決定します。
```

### E-2: 将来シナリオでの手動入力値優先

`pages/page_forecast.py` を改修し、説明変数の将来値について:
- 入力フィールドに値が入力されている場合: その値を使用
- 入力フィールドが空欄の場合: ARIMA予測値を自動入力（フォールバック）

```
説明変数の将来値入力（手動入力が優先）
変数名          | 2026年度 | 2027年度 | 2028年度 | ARIMAから自動入力
unemployment    | [    ]   | [    ]   | [    ]   | [ARIMAを適用]
gdp_growth      | [1.2 ]   | [1.5 ]   | [1.3 ]   | ←手動入力済み
```

---

## Phase 6F: 解釈説明・マニュアル充実

### F-1: 各ページのインライン説明強化

ヘルプパネル（`components/help_panel.py`）の内容を充実させる。

| ページ | 追加すべき説明 |
|--------|-------------|
| ③回帰分析 | 交差検証の分割数の意味（5-Fold = 全データを5分割し、4/5で学習・1/5で検証を5回繰り返す）|
| ③回帰分析 | 残差プロットの見方・判断基準（ランダムに散らばっているか、パターンがないか）|
| ③回帰分析 | 残差ヒストグラムの見方（正規分布に近いか）|
| ③回帰分析 | 交差検証の各fold MSE・標準偏差の解釈 |
| ⑤動的回帰 | 目的変数の変換・標準化を行わない理由の説明 |
| ⑥ARIMA | ARIMAモデルの基本概念（p, d, q の意味）|
| ⑥ARIMA | ADF検定の解釈方法（p値<0.05で定常性あり）|
| ⑥ARIMA | ACF/PACFグラフの読み方 |
| ⑥ARIMA | nlagsの設定目安 |

### F-2: 実務担当者向けARIMAマニュアル追加

`docs/operation_manual.md` に「ARIMAページの操作手順」セクションを追加。

```
セクション構成:
  1. ARIMAとは何か（一言説明）
  2. このページで何をするか（年次運用での役割）
  3. ADF検定の手順と結果の読み方
  4. ACF/PACFグラフの見方と次数(p,d,q)の選び方
  5. ARIMA推定の実行と結果の確認
  6. 予測の実行と予測区間の解釈
  7. よくあるトラブルと対処方法
```

### F-3: `docs/interpretation_manual.md` 拡張

既存の統計結果解釈マニュアルに以下を追加:
- 交差検証の詳細解釈（fold別MSE、標準偏差の判断基準）
- ARIMAモデルの診断（残差の正規性・独立性の確認方法）
- 動的回帰での目的変数の変換を行わない理由

---

## Phase 5: ECL算出機能（既存計画を維持）

Phase 6完了後に着手する。設計は既存計画書の内容を維持。

### 5-1. DB拡張 — `db/migrations/004_create_ecl_tables.sql`

新規テーブル:
- `arima_forecasts`: ARIMA予測結果の保存先
- `ecl_results`: ECL計算結果の保存先

既存テーブル（そのまま利用）:
- `model_configs` / `model_results`

### 5-2〜5-6: コアロジック・UI実装

| Phase | ファイル | 内容 |
|-------|---------|------|
| 5-2 | `src/analysis/ecl.py` | ECL計算コアロジック（UI非依存） |
| 5-3 | `src/db_operations.py` | モデル・ARIMA・ECL結果のDB保存/読込 |
| 5-4 | `pages/page_arima.py` | 「予測結果をDBに保存」ボタンを追加 |
| 5-5 | `pages/page_model_confirm.py` | ⑦モデル確定タブ（新規） |
| 5-6 | `pages/page_ecl.py` | ⑧ECL計算タブ（page_forecast.py置換） |
| 5-7 | `docs/` | ドキュメント更新 |

Phase 5の詳細設計（DB構造・関数仕様・UI設計）は本ファイルの末尾に記載。

---

## タブ構成（Phase 5完了後: 9タブ）

| # | タブ名 | ファイル | 主な機能 | 状態 |
|---|--------|---------|---------|------|
| ① | データ閲覧 | `page_data_view.py` | データセット確認・CSVインポート・**比較プロット（6D）** | 6D対応予定 |
| ② | 相関分析 | `page_correlation.py` | 相関行列・VIF・**新式UI（6B）** | 6B対応予定 |
| ③ | 回帰分析 | `page_regression.py` | OLS回帰・残差プロット・交差検証・**新式UI（6B）** | 6B対応予定 |
| ④ | モデル選択 | `page_model_selection.py` | 全組み合わせ探索・**新式UI・表示改善（6B）** | 6B対応予定 |
| ⑤ | 動的回帰 | `page_dynamic_regression.py` | 変数別ラグ・変換設定（現状維持・注記追加） | 6C対応予定 |
| ⑥ | ARIMA | `page_arima.py` | ADF検定・ACF/PACF・次数選択・**nlags改善（6E）**・**予測保存（5-4）** | 6E/5-4対応予定 |
| ⑦ | モデル確定 | `page_model_confirm.py` | 回帰モデルのDB登録・一覧管理 | 未着手（5-5） |
| ⑧ | ECL計算 | `page_ecl.py` | シナリオ設定・ECL計算・結果保存 | 未着手（5-6） |

---

## 実装順序サマリー

```
Phase 6A（バグ修正）              ← 最優先。すぐに着手
  ↓
Phase 6B（UI統一）                ← 6A完了後
  ↓
Phase 6C（設計変更・注記追加）    ← コード変更が少ない。6Bと並行可
  ↓
Phase 6D（データ閲覧拡張）        ← 6B完了後
  ↓
Phase 6E（ARIMA改善）             ← 6A完了後（6Dと並行可）
  ↓
Phase 6F（ドキュメント充実）      ← 随時。6E完了後にまとめて実施
  ↓
Phase 5（ECL算出機能）            ← Phase 6完了後
```

---

## Phase 5 詳細設計（参考：変更なし）

### 5-1. DB拡張 — `db/migrations/004_create_ecl_tables.sql`

```sql
CREATE TABLE arima_forecasts (
    forecast_id         SERIAL PRIMARY KEY,
    indicator_code      VARCHAR(100) NOT NULL,
    dataset_id          INTEGER REFERENCES indicator_datasets(dataset_id),
    frequency           VARCHAR(20) NOT NULL,
    arima_order         VARCHAR(20) NOT NULL,
    forecast_steps      INTEGER NOT NULL,
    forecast_data       JSONB NOT NULL,
    scenario_label      VARCHAR(50),
    note                TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ecl_results (
    ecl_id              SERIAL PRIMARY KEY,
    model_config_id     INTEGER REFERENCES model_configs(config_id),
    target_dataset_id   INTEGER REFERENCES target_datasets(target_dataset_id),
    segment_code        VARCHAR(50) NOT NULL DEFAULT 'all',
    target_code         VARCHAR(100) NOT NULL,
    fiscal_year_month   DATE,
    weight_base         NUMERIC(5,4) NOT NULL,
    weight_upside       NUMERIC(5,4) NOT NULL,
    weight_downside     NUMERIC(5,4) NOT NULL,
    results             JSONB NOT NULL,
    note                TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5-2. `src/analysis/ecl.py` — 関数シグネチャ

```python
def apply_model_to_forecast(model_result: dict, forecast_df: pd.DataFrame) -> pd.DataFrame:
    """確定済み回帰モデルにARIMA予測値を代入し、PD/LGD予測値を計算する"""

def calc_weighted_ecl(
    base_pd, upside_pd, downside_pd,
    base_lgd, upside_lgd, downside_lgd,
    weight_base, weight_upside, weight_downside
) -> dict:
    """3シナリオの加重平均でECL期待値を計算する"""

def build_scenario_forecast(arima_forecasts: dict, scenario: str) -> pd.DataFrame:
    """説明変数ごとのARIMA予測結果から、指定シナリオの説明変数DataFrameを組み立てる"""
```

### 5-3. `src/db_operations.py` 拡張関数一覧

```python
# モデル確定
save_model_config(config_dict) -> int
save_model_result(config_id, result_dict) -> int
load_model_configs() -> pd.DataFrame
load_model_result(config_id) -> dict

# ARIMA予測
save_arima_forecast(forecast_dict) -> int
load_arima_forecasts(indicator_code=None) -> pd.DataFrame
load_arima_forecast_data(forecast_id) -> pd.DataFrame

# ECL結果
save_ecl_result(ecl_dict) -> int
load_ecl_results() -> pd.DataFrame
```

### 5-5. ⑦モデル確定タブ UI構成

```
────────────────────────────────────────
 データソース選択（DataSourceSelectorを再利用）
────────────────────────────────────────
 目的変数・説明変数の選択
────────────────────────────────────────
 モデル設定（ラグ・変換・メモ）
────────────────────────────────────────
 [回帰を実行して確認]
────────────────────────────────────────
 回帰結果プレビュー（Adj.R² / AIC / DW / 係数テーブル）
────────────────────────────────────────
 [このモデルをDBに保存]
────────────────────────────────────────
 保存済みモデル一覧
  config_id | 目的変数 | 説明変数 | Adj.R² | 保存日 | [削除]
────────────────────────────────────────
```

### 5-6. ⑧ECL計算タブ UI構成

```
────────────────────────────────────────
 Step 1: 回帰モデルの選択（保存済みモデル一覧ドロップダウン）
────────────────────────────────────────
 Step 2: 説明変数ごとのARIMA予測の割り当て
  変数名 | ARIMA予測（保存済みforecast_id） | シナリオ対応
────────────────────────────────────────
 Step 3: シナリオウェイト（ベース/楽観/悲観、合計100%チェック）
────────────────────────────────────────
 Step 4: 予測期間・EAD設定
────────────────────────────────────────
 [ECLを計算する]
────────────────────────────────────────
 計算結果（シナリオ別グラフ・結果テーブル）
 [結果をDBに保存] [CSVエクスポート]
────────────────────────────────────────
```

---

## 年次運用ワークフロー（Phase 5完了後）

```
毎年度の引当金計算フロー:

【データ更新】
  ① データ閲覧タブ
      - 最新の説明変数CSVをインポート
      - PD/LGD実績値のCSVをレコード追加インポート（6D後）

【モデル探索（必要な年のみ）】
  ② 相関分析 → ④ モデル選択 → ③ 回帰分析 → ⑤ 動的回帰

【ARIMA予測（毎年実施）】
  ⑥ ARIMAタブ
      - 各説明変数について最新データでARIMAを再推定
      - 予測結果をDBに保存

【モデル確定（必要な年のみ）】
  ⑦ モデル確定タブ
      - 前年のconfig_idを流用するか、新規登録するか選択

【ECL計算（毎年実施）】
  ⑧ ECL計算タブ
      - config_id + forecast_id を選択
      - シナリオウェイト・EADを設定して計算・保存
```

---

## 検証方法

1. **Phase 6A**: 各修正後に該当ページで動作確認
2. **Phase 6B**: 全3ページで新式UI動作確認、既存機能の回帰テスト
3. **Phase 5**: E2Eフロー検証（CSV → 分析 → モデル確定 → ARIMA予測保存 → ECL計算 → CSV出力）

---

## Phase W: Web公開（Render + Supabase）（2026-03-11 追加）

### アーキテクチャ

```
[ローカル開発]                    [Web公開]
  Fletデスクトップ                  Flet Webモード
  + config/db.ini                   + Render環境変数
  + ローカルPostgreSQL              + Supabase (PostgreSQL)
```

**設計方針**: ローカル開発フローは一切壊さない。環境変数の有無で自動切替。

### セキュリティ設計

| 項目 | 方針 |
|------|------|
| DB接続情報 | Render環境変数で管理（暗号化保存） |
| `config/db.ini` | .gitignore済み（ローカル専用） |
| `.env` | .gitignoreに追加（ローカルテスト用） |
| service_role key | Render環境変数のみ、絶対にGitに入れない |
| Supabase RLS | 全テーブルに設定（用途に応じてポリシー定義） |
| GitHubリポジトリ | private推奨 |

---

### W1: DB接続二重化（環境変数フォールバック）

**変更ファイル**: `config/db.py` のみ

**変更内容**:
```python
# _load_config() のロジック変更:
# 1. db.ini が存在する → 従来通り configparser で読む
# 2. db.ini が存在しない → os.environ から読む
#    - DATABASE_URL があれば → パースして接続パラメータに変換
#    - 個別環境変数 (DB_HOST等) があれば → dictに変換
# 3. どちらも無い → FileNotFoundError（従来と同じ）

# get_connection() の変更:
# - Supabase接続時は sslmode=require が必要
# - cfg に "sslmode" キーがあれば connect() に渡す
```

**ポイント**:
- `get_connection()` のインターフェースは不変 → 呼び出し側7ファイルの変更不要
- Supabase pooler (port 6543, Transaction mode) では `SET search_path` がリセットされる
- → Session mode (port 5432) を使用するか、各クエリでスキーマを明示指定

---

### W2: main.py Web/デスクトップ切替

**変更ファイル**: `main.py` のみ

**変更内容**:
```python
# 1. page.window.* 設定を条件分岐でガード
if not page.web:  # デスクトップ時のみ
    page.window.resizable = True
    page.window.width = 1400
    ...

# 2. エントリポイント切替
if __name__ == "__main__":
    import os
    if os.environ.get("FLET_WEB", "").strip() == "1":
        ft.app(target=main, view=ft.AppView.WEB_BROWSER,
               port=int(os.environ.get("PORT", "8550")))
    else:
        ft.run(main)  # 従来のデスクトップモード
```

**ポイント**: Renderは `PORT` 環境変数を自動設定する

---

### W3: Supabase DBセットアップ（手動作業）

**作業手順**:
1. Supabaseプロジェクト作成
2. SQL Editorで `db/migrations/001〜005` を順番に実行
3. RLSポリシー設定（`db/migrations/006_supabase_rls_setup.sql` を新規作成・実行）
4. 接続文字列を取得（Project Settings > Database > Connection string）

**新規ファイル**: `db/migrations/006_supabase_rls_setup.sql`

**注意点**:
- Supabaseのデフォルトdb名は `postgres`（ローカルの `craft` ではない）
- `CREATE SCHEMA IF NOT EXISTS calc_ecl` で対応可能
- SERIAL, JSONB, GIN INDEX, BYTEA 全てSupabase互換

---

### W4: Renderデプロイ設定

**新規ファイル**:

1. `render.yaml` — Render Blueprint
```yaml
services:
  - type: web
    name: calc-ecl
    runtime: python
    buildCommand: pip install -r requirements-web.txt
    startCommand: python main.py
    envVars:
      - key: FLET_WEB
        value: "1"
      - key: DATABASE_URL
        sync: false  # Render dashboardで手動設定
      - key: DB_SCHEMA
        value: calc_ecl
```

2. `requirements-web.txt` — Web版用依存パッケージ
   - `requirements.txt` から `flet-desktop==0.81.0` と `flet-cli==0.81.0` を除外
   - それ以外はそのまま

**変更ファイル**: `.gitignore` に `.env` を追加

**日本語フォント対応**:
- Render build command に `apt-get install -y fonts-noto-cjk` が必要
- または `render.yaml` の `buildCommand` を拡張

---

### W5: FilePickerのWeb対応（最大の改修ポイント）

**変更ファイル**:
- `pages/page_data_view.py`
- `src/import_indicators.py`
- `src/import_targets.py`

**問題**: Flet WebではFilePickerがアップロード方式に変わる。`files[0].path` でローカルパスを直読みするコードが動かない。

**解決方針**:
1. `page.web` で分岐
   - デスクトップ時: 従来通り `files[0].path`
   - Web時: `ft.FilePickerUploadFile` でアップロード → 一時ファイルとして処理
2. `import_indicators.py` / `import_targets.py` の `import_csv()` シグネチャ拡張:
   - `csv_path: str | None = None, csv_content: str | None = None`
   - パスが渡されたら従来通り、contentが渡されたら `io.StringIO` で処理

**代替案**: WebではテキストエリアにCSVを貼り付ける方式（Flet Web FilePickerの挙動が不安定な場合）

---

### W6: ドキュメント更新

| ファイル | 追記内容 |
|---------|---------|
| `docs/system_manual.md` | Web版アーキテクチャ・デプロイ手順 |
| `docs/operation_manual.md` | Web版アクセス方法・CSVインポート操作変更 |
| `CLAUDE.md` | Web版の設計原則とデプロイターゲット |
| `docs/implementation_plan.md` | Phase W進捗更新 |

---

### Phase W 実装順序

```
W1（DB接続二重化）     ← 最初。既存コード影響ゼロ
  ↓
W2（Web起動切替）       ← main.py のみ
  ↓
W3（Supabase構築）      ← 手動作業。Supabaseアカウント必要
  ↓
W4（Renderデプロイ）    ← 新規ファイル追加のみ
  ↓
  ★ デプロイ検証（CSVインポート以外の全機能をWeb上で確認）
  ↓
W5（FilePicker対応）    ← 最もリスク高。検証後に着手
  ↓
W6（ドキュメント）      ← 最後
```

### 潜在的な課題

| 課題 | リスク | 対策 |
|------|--------|------|
| Flet 0.81.0 Webモードの安定性 | 中 | show_dialog/TabBar等のWeb挙動を要検証 |
| Render無料枠のRAM (512MB) | 中 | pandas/statsmodels/matplotlibが重い。メモリ不足時はプラン変更検討 |
| 日本語フォント | 低 | build commandでfonts-noto-cjk インストール |
| Supabase接続プール | 中 | Session mode (port 5432) を使用 |
| BYTEA列 (model_binary) | 低 | 大きなpickleオブジェクトの格納制限確認が必要 |
