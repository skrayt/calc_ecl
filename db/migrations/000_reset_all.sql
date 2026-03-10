-- =============================================================
-- calc_ecl スキーマ 完全初期化スクリプト
-- PostgreSQL 15
-- DB名: craft  スキーマ: calc_ecl
--
-- ⚠️  警告: このスクリプトは calc_ecl スキーマの全データを削除します ⚠️
--
-- 実行方法: PgAdmin4 で本ファイルの内容を貼り付けて実行する
-- 実行後: 001 → 002 → 003 の順にマイグレーションを実行する
-- =============================================================

SET search_path TO calc_ecl;

-- =============================================================
-- Step 1: 全テーブルを外部キー依存の逆順で削除
-- =============================================================

DROP TABLE IF EXISTS forecast_scenarios   CASCADE;
DROP TABLE IF EXISTS model_results        CASCADE;
DROP TABLE IF EXISTS model_configs        CASCADE;
DROP TABLE IF EXISTS indicator_data       CASCADE;
DROP TABLE IF EXISTS indicator_datasets   CASCADE;
DROP TABLE IF EXISTS indicator_definitions CASCADE;
DROP TABLE IF EXISTS target_data          CASCADE;
DROP TABLE IF EXISTS target_datasets      CASCADE;
DROP TABLE IF EXISTS target_definitions   CASCADE;
DROP TABLE IF EXISTS indicator_sources    CASCADE;

-- =============================================================
-- Step 2: スキーマごと削除して再作成（シーケンスもリセット）
-- =============================================================

DROP SCHEMA IF EXISTS calc_ecl CASCADE;
CREATE SCHEMA calc_ecl;
SET search_path TO calc_ecl;

-- =============================================================
-- 以降は 001 → 002 → 003 の順に実行してください
-- =============================================================
