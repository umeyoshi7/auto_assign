# HPLC ピーク集計ツール

HPLCチャートから得られた複数サンプルのRT/%Areaデータを、RRT（相対保持時間）基準でピーク揃えして集計する Streamlit アプリです。

## 機能

- 最大30ファイルの CSV を一括アップロード
- ファイルごとにメインピークを選択し、RRT を自動計算
- RRTのグリーディ割り付けにより、サンプル間でピークを対応付けして集計
- `tolerance`（RRT偏差）をリアルタイムに変更 → 集計結果が即時更新
- 結果を UTF-8 BOM 付き CSV でダウンロード

## 起動方法

```bash
# 依存パッケージのインストール
pip install streamlit pandas numpy

# 起動
streamlit run app.py
```

## CSV フォーマット

```
RT,1.702,3.63,8.686,...
%Area,2.44,0.30,0.73,...
```

- 1行目: `RT` から始まり、各ピークの保持時間をカンマ区切りで記載
- 2行目: `%Area` から始まり、各ピークの面積百分率をカンマ区切りで記載
- エンコーディング: UTF-8

## ファイル構成

```
app.py                  # Streamlit アプリ本体
generate_test_data.py   # テストデータ生成スクリプト
test_data/              # サンプル CSV (sample_01.csv 〜 sample_10.csv)
```

## テストデータの生成

```bash
python generate_test_data.py
```

`test_data/` ディレクトリに `sample_01.csv` 〜 `sample_10.csv` が生成されます。
