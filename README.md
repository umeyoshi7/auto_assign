# HPLC ピーク集計ツール

HPLCチャートから得られた複数サンプルのRT/%Areaデータを、RRT（相対保持時間）基準でピーク揃えして集計する Streamlit アプリです。

## 機能

- 最大30ファイルの CSV を一括アップロード
- ファイルごとにメインピークを選択し、RRT を自動計算
- RRTのグリーディ割り付けにより、サンプル間でピークを対応付けして集計
- `tolerance`（RRT偏差）をリアルタイムに変更 → 集計結果が即時更新
- 結果を UTF-8 BOM 付き CSV でダウンロード
- **OCR機能**: 島津・Waters 機種のHPLCレポートPDFから Azure OpenAI Vision API でピークデータを自動抽出

## 起動方法

```bash
# 依存パッケージのインストール
pip install streamlit pandas numpy

# OCR機能も使う場合
pip install pymupdf openai

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

## OCR 機能

### Azure OpenAI の設定

`.streamlit/secrets.toml` に以下を記載してください（`.streamlit/secrets.toml.example` を参照）:

```toml
AZURE_OPENAI_KEY = "your-api-key"
AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
AZURE_OPENAI_DEPLOYMENT = "gpt-4o"  # 省略時デフォルト
```

### 対応機種

| 機種 | 列名変換 |
|------|---------|
| 島津 | 「保持時間」→ RT、「面積%」→ %Area |
| Waters | 「保持時間(分)」→ RT、「%面積」→ %Area |

### OCR からピーク集計への手順

1. 「OCR機能」タブで PDF をアップロードし、機種を選択して「OCR実行」
2. 抽出結果プレビュー（行: RT / %Area、列: ピーク番号）で内容を確認
3. 「ピーク集計」タブのサイドバーで「OCR結果を利用」を選択
4. multiselect で集計に使用するサンプルを選択
5. 基準データ・メインピーク・RRT偏差を設定して集計結果を確認

## ファイル構成

```
app.py                          # Streamlit アプリ本体
generate_test_data.py           # テストデータ生成スクリプト
test_data/                      # サンプル CSV (sample_01.csv 〜 sample_10.csv)
.streamlit/secrets.toml         # Azure OpenAI APIキー（要作成、gitignore推奨）
.streamlit/secrets.toml.example # 設定例
```

## テストデータの生成

```bash
python generate_test_data.py
```

`test_data/` ディレクトリに `sample_01.csv` 〜 `sample_10.csv` が生成されます。
