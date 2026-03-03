# CLAUDE.md

## プロジェクト概要

HPLCピーク集計 Streamlit アプリ。`app.py` 1ファイル構成。

## 開発環境

- Python 3.12+、仮想環境: `.venv/`
- 主要ライブラリ: `streamlit==1.54.0`、`pandas`、`numpy`
- 起動: `streamlit run app.py`
- テストデータ生成: `python generate_test_data.py`

## アーキテクチャ

```
parse_csv()                  # CSV bytes → DataFrame(RT, %Area)
compute_rrt()                # DataFrame + main_rt → RRT列を追加
build_aggregation_table()    # @st.cache_data。RRTグリーディ割り付けで集計テーブル生成
ocr_reports_to_dataframes()  # reports リスト → {サンプル名: DataFrame(RT, %Area)}
                             # rt→RT, area_pct→%Area に列名変換済み
main()                       # Streamlit UI。ファイルアップロード後は常時集計（ボタンなし）
```

`build_aggregation_table` は `dict` の代わりに `tuple(sorted(items()))` を受け取る（`@st.cache_data` のハッシュ制約）。

### OCRプレビュー
- `st.dataframe(df.T)` で転置表示（行=RT/%Area、列=ピーク番号）し、集計タブと同形式で確認できる

### OCRデータ選択
- 「ピーク集計」タブで「OCR結果を利用」選択時、`st.multiselect` でサンプルを選択・除外できる

### サイドバーのデータ形式例
- `with st.expander("使用可能な表データ形式の例"):` でCSV/OCR両形式の入力例を常時表示（データ未読み込み時も表示）

## コーディング規則

- 変更は最小限に。既存ロジックを壊さない範囲で修正する
- UI テキスト・コメントは日本語
- `st.error` / `st.warning` でユーザーへのフィードバックを返す
- ファイル読み込みは `uf.getvalue()`（`uf.read()` はポインタが戻らないため使わない）
