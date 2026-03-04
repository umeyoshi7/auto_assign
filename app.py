import base64
import io
import json
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

try:
    import fitz  # pymupdf
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

try:
    import openai
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


# ───────────────────────────────────────────────────────────
# データ読み込み
# ───────────────────────────────────────────────────────────

def parse_csv(file_bytes: bytes, filename: str) -> Optional[pd.DataFrame]:
    """
    CSVを解析して DataFrame(columns=["RT", "%Area"]) を返す。
    フォーマット:
        1行目: RT,val1,val2,...
        2行目: %Area,val1,val2,...
    エラー時は None を返す。
    """
    try:
        text = file_bytes.decode("utf-8")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) < 2:
            st.error(f"{filename}: 行数が足りません")
            return None

        rt_parts = lines[0].split(",")
        area_parts = lines[1].split(",")

        if rt_parts[0].strip().upper() != "RT":
            st.error(f"{filename}: 1行目が 'RT' から始まっていません")
            return None
        if area_parts[0].strip().replace(" ", "") not in ("%Area", "%AREA", "%area"):
            st.error(f"{filename}: 2行目が '%Area' から始まっていません")
            return None

        rts = [float(v) for v in rt_parts[1:]]
        areas = [float(v) for v in area_parts[1:]]

        if len(rts) != len(areas):
            st.error(f"{filename}: RT と %Area の列数が一致しません")
            return None

        return pd.DataFrame({"RT": rts, "%Area": areas})

    except Exception as e:
        st.error(f"{filename}: 解析エラー — {e}")
        return None


# ───────────────────────────────────────────────────────────
# OCR関連関数
# ───────────────────────────────────────────────────────────

def get_azure_client():
    """Azure OpenAI クライアントを返す。設定がない場合は None。"""
    if not _OPENAI_AVAILABLE:
        st.error("openai パッケージがインストールされていません。`pip install openai` を実行してください。")
        return None
    try:
        key = st.secrets["AZURE_OPENAI_KEY"]
        endpoint = st.secrets["AZURE_OPENAI_ENDPOINT"]
    except (KeyError, FileNotFoundError):
        st.error(
            "Azure OpenAI の設定が見つかりません。"
            "`.streamlit/secrets.toml` に `AZURE_OPENAI_KEY` と `AZURE_OPENAI_ENDPOINT` を設定してください。"
        )
        return None
    try:
        api_version = st.secrets["AZURE_OPENAI_API_VERSION"]
    except (KeyError, FileNotFoundError):
        api_version = "2024-02-15-preview"
    return openai.AzureOpenAI(
        api_key=key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )


def pdf_to_base64_images(pdf_bytes: bytes) -> list[str]:
    """PDFの各ページを 150dpi PNG に変換して base64 文字列のリストを返す。"""
    if not _FITZ_AVAILABLE:
        st.error("pymupdf パッケージがインストールされていません。`pip install pymupdf` を実行してください。")
        return []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images_b64 = []
    mat = fitz.Matrix(150 / 72, 150 / 72)  # 150dpi
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        images_b64.append(base64.b64encode(png_bytes).decode("utf-8"))
    doc.close()
    return images_b64


def build_shimazu_prompt() -> str:
    """島津レポート用OCRプロンプトを返す。"""
    return """あなたはHPLCクロマトグラフィーレポートの読み取り専門家です。
提供された画像はスキャンされたPDFの各ページです。

【抽出ルール】
1. 各ページ上部の「サンプル名：」の右側にある文字列をサンプル名として読み取る
2. 表データから「保持時間」「面積」「面積%」「化合物名」列を読み取る（「合計」行は除外）
3. 「化合物名」は手書きの場合があるため、丁寧に読み取ること
4. ページ下部のファイル名（例：LC-034R-202621810.lcd）が同じで、かつ「ピーク」列の番号が連続しているページは同一レポートとして統合する
5. 1つのPDFに複数レポートが含まれる場合は、それぞれ別々に返す（最大30レポート）

【出力形式】必ずJSON形式で返すこと:
{
  "reports": [
    {
      "sample_name": "サンプル名の値",
      "report_id": "ページ下部のファイル名",
      "peaks": [
        {
          "peak_no": 1,
          "rt": 1.234,
          "area": 123456,
          "area_pct": 0.12,
          "compound_name": "化合物名または空文字"
        }
      ]
    }
  ]
}"""


def build_waters_prompt() -> str:
    """Waters レポート用OCRプロンプトを返す。"""
    return """あなたはHPLCクロマトグラフィーレポートの読み取り専門家です。
提供された画像はスキャンされたPDFの各ページです。

【抽出ルール】
1. 各ページ上部の「サンプル名：」の右側にある文字列をサンプル名として読み取る
2. 表データから「保持時間(分)」「面積(μV秒)」「%面積」「化合物名」列を読み取る
3. 「化合物名」は手書きの場合があるため、丁寧に読み取ること
4. ページ下部の「結果ID」の右隣の文字列が同じで、かつ先頭連番列の番号が連続しているページは同一レポートとして統合する
5. 1つのPDFに複数レポートが含まれる場合は、それぞれ別々に返す（最大30レポート）

【出力形式】必ずJSON形式で返すこと:
{
  "reports": [
    {
      "sample_name": "サンプル名の値",
      "result_id": "結果IDの値",
      "peaks": [
        {
          "peak_no": 1,
          "rt": 1.234,
          "area": 123456,
          "area_pct": 0.12,
          "compound_name": "化合物名または空文字"
        }
      ]
    }
  ]
}"""


def run_ocr(images_b64: list[str], prompt: str, client, deployment: str) -> Optional[list[dict]]:
    """全画像を Azure OpenAI に送信してピーク情報を抽出する。"""
    content = [{"type": "text", "text": prompt}]
    for img_b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
        })
    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=4096,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return data.get("reports", [])
    except Exception as e:
        st.error(f"OCR実行エラー — {e}")
        return None


def ocr_reports_to_dataframes(reports: list[dict]) -> dict[str, pd.DataFrame]:
    """reports リストをサンプル名 → DataFrame(RT, %Area) の辞書に変換する。"""
    result: dict[str, pd.DataFrame] = {}
    for report in reports:
        sample_name = report.get("sample_name") or "不明"
        peaks = report.get("peaks", [])
        if not peaks:
            continue
        rows = []
        for p in peaks:
            try:
                rt = float(p["rt"])
                area_pct = float(p["area_pct"])
                rows.append({"RT": rt, "%Area": area_pct})
            except (KeyError, TypeError, ValueError):
                continue
        if not rows:
            continue
        df = pd.DataFrame(rows)

        # 同名サンプルが複数ある場合は接尾辞を付与
        if sample_name not in result:
            result[sample_name] = df
        else:
            suffix = 2
            while f"{sample_name}_{suffix}" in result:
                suffix += 1
            result[f"{sample_name}_{suffix}"] = df
    return result


# ───────────────────────────────────────────────────────────
# RRT割り付けアルゴリズム
# ───────────────────────────────────────────────────────────

def compute_rrt(df: pd.DataFrame, main_rt: float) -> pd.DataFrame:
    """各行に RRT 列を追加して返す。"""
    df = df.copy()
    df["RRT"] = df["RT"] / main_rt
    return df


@st.cache_data
def build_aggregation_table(
    datasets_tuple: tuple,  # ((name, df), ...) ← dict は unhashable なので tuple に変換
    ref_name: str,
    tolerance: float,
) -> pd.DataFrame:
    """
    RRTグリーディ割り付けで集計テーブルを構築する。
    行: ファイル名 (基準データ先頭)
    列: RRT値 (float, 4桁)
    値: %Area
    """
    datasets = dict(datasets_tuple)
    # 基準データを先頭に並べ替え
    names = [ref_name] + [n for n in datasets if n != ref_name]

    # Step 2 — 基準データのRRT列を確定
    ref_rrts = sorted(datasets[ref_name]["RRT"].tolist())
    columns: list[float] = list(ref_rrts)  # 列ヘッダー (RRT値)

    # Step 3 — 他データを列にグリーディ割り付け
    for name in names[1:]:
        df = datasets[name]
        other_rrts = sorted(df["RRT"].tolist())
        used_cols: set[float] = set()

        for o_rrt in other_rrts:
            candidates = [
                c for c in columns
                if abs(c - o_rrt) <= tolerance and c not in used_cols
            ]
            if candidates:
                closest = min(candidates, key=lambda c: abs(c - o_rrt))
                used_cols.add(closest)
            else:
                # 新規列を挿入
                columns.append(o_rrt)
                used_cols.add(o_rrt)
                # 列をRRT順にソート
                columns.sort()

    # Step 4 — テーブル構築
    col_headers = [f"{c:.4f}" for c in columns]  # 列ヘッダー (文字列)
    col_to_header: dict[float, str] = {c: h for c, h in zip(columns, col_headers)}

    rows = []
    for name in names:
        df = datasets[name]
        other_rrts = sorted(df["RRT"].tolist())
        used_cols: set[float] = set()

        # 各RRTをどの列に対応させるか決定
        rrt_to_col: dict[float, float] = {}
        for o_rrt in other_rrts:
            candidates = [
                c for c in columns
                if abs(c - o_rrt) <= tolerance and c not in used_cols
            ]
            if candidates:
                closest = min(candidates, key=lambda c: abs(c - o_rrt))
                rrt_to_col[o_rrt] = closest
                used_cols.add(closest)

        # 列ヘッダー(文字列)に対応する %Area を取得
        row: dict[str, Optional[float]] = {h: None for h in col_headers}
        for _, peak in df.iterrows():
            rrt = peak["RRT"]
            col = rrt_to_col.get(rrt)
            if col is not None:
                row[col_to_header[col]] = peak["%Area"]

        rows.append(row)

    # DataFrame化
    result = pd.DataFrame(rows, index=names, columns=col_headers)
    result.index.name = "ファイル名"
    return result


# ───────────────────────────────────────────────────────────
# Streamlit UI
# ───────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="HPLC集計", layout="wide")
    st.title("HPLC ピーク集計ツール (RRT基準)")

    tab_ocr, tab_aggregate = st.tabs(["OCR機能", "ピーク集計"])

    # ── OCR タブ ─────────────────────────────────────────────
    with tab_ocr:
        st.header("HPLCチャートOCR")

        if not _FITZ_AVAILABLE or not _OPENAI_AVAILABLE:
            missing = []
            if not _FITZ_AVAILABLE:
                missing.append("pymupdf")
            if not _OPENAI_AVAILABLE:
                missing.append("openai")
            st.warning(f"必要なパッケージがインストールされていません: {', '.join(missing)}\n`pip install {' '.join(missing)}` を実行してください。")

        pdf_file = st.file_uploader("PDFファイルをアップロード", type=["pdf"])
        device = st.radio("機種選択", ["島津", "Waters"], horizontal=True)

        if st.button("OCR実行") and pdf_file:
            with st.spinner("OCR実行中..."):
                client = get_azure_client()
                if client is not None:
                    try:
                        deployment = st.secrets.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
                    except Exception:
                        deployment = "gpt-4o"

                    images_b64 = pdf_to_base64_images(pdf_file.getvalue())
                    if images_b64:
                        prompt = build_shimazu_prompt() if device == "島津" else build_waters_prompt()
                        reports = run_ocr(images_b64, prompt, client, deployment)
                        if reports is not None:
                            results = ocr_reports_to_dataframes(reports)
                            if results:
                                st.session_state["ocr_results"] = results
                                st.success(f"{len(results)}件のレポートを抽出しました")
                            else:
                                st.warning("レポートデータを抽出できませんでした。")

        # 既存 OCR 結果がある場合はプレビューを常時表示
        if "ocr_results" in st.session_state:
            st.subheader("抽出結果プレビュー")
            st.caption("行：項目名（RT / %Area）、列：ピーク番号")
            for name, df in st.session_state["ocr_results"].items():
                st.markdown(f"**{name}**")
                st.dataframe(df.T, use_container_width=True)

    # ── 集計タブ ─────────────────────────────────────────────
    with tab_aggregate:
        # ── サイドバー ──
        with st.sidebar:
            st.header("設定")

            data_source = st.radio(
                "データソース",
                ["ローカルCSVファイル", "OCR結果を利用"],
            )

            if data_source == "ローカルCSVファイル":
                uploaded_files = st.file_uploader(
                    "CSVファイルをアップロード (最大30ファイル)",
                    type=["csv"],
                    accept_multiple_files=True,
                )

                if not uploaded_files:
                    st.info("CSVファイルをアップロードしてください。")
                    raw_data = None
                else:
                    if len(uploaded_files) > 30:
                        st.warning("30ファイルを超えています。最初の30ファイルのみ使用します。")
                        uploaded_files = uploaded_files[:30]

                    raw_data: dict[str, pd.DataFrame] = {}
                    for uf in uploaded_files:
                        df = parse_csv(uf.getvalue(), uf.name)
                        if df is not None:
                            raw_data[uf.name] = df

                    if not raw_data:
                        st.error("有効なCSVファイルがありません。")
                        raw_data = None
                    else:
                        st.success(f"{len(raw_data)} ファイル読み込み済み")
                        st.markdown("**読み込み済みファイル:**")
                        for name in raw_data:
                            st.markdown(f"- {name}")

            else:  # OCR結果を利用
                ocr_results = st.session_state.get("ocr_results")
                if not ocr_results:
                    st.warning("OCR結果がありません。先に「OCR機能」タブでOCRを実行してください。")
                    raw_data = None
                else:
                    all_names = list(ocr_results.keys())
                    selected_names = st.multiselect(
                        "集計に使用するサンプルを選択",
                        options=all_names,
                        default=all_names,
                    )
                    if not selected_names:
                        st.warning("サンプルを1つ以上選択してください。")
                        raw_data = None
                    else:
                        raw_data = {name: ocr_results[name] for name in selected_names}
                        st.success(f"{len(raw_data)} サンプル選択済み（OCR結果）")
                        for name in raw_data:
                            st.markdown(f"- {name}")

            if raw_data:
                st.divider()

                # ── 基準データ選択 ──
                ref_name = st.selectbox(
                    "基準データ",
                    options=list(raw_data.keys()),
                    index=0,
                )

                st.divider()

                # ── メインピーク選択 ──
                st.subheader("メインピーク選択")
                main_rt_map: dict[str, float] = {}
                for name, df in raw_data.items():
                    default_rt = df.loc[df["%Area"].idxmax(), "RT"]
                    rt_options = df["RT"].tolist()
                    default_idx = rt_options.index(default_rt)
                    selected_rt = st.selectbox(
                        f"{name}",
                        options=rt_options,
                        index=default_idx,
                        format_func=lambda x: f"{x:.3f}",
                        key=f"main_rt_{name}",
                    )
                    main_rt_map[name] = selected_rt

                st.divider()

                # ── RRT偏差 ──
                tolerance = st.number_input(
                    "RRT偏差 (tolerance)",
                    min_value=0.001,
                    max_value=0.100,
                    value=0.005,
                    step=0.001,
                    format="%.3f",
                    help="この範囲内のRRT差を同一ピークとみなします",
                )

                st.divider()

            st.divider()
            with st.expander("使用可能な表データ形式の例"):
                st.markdown(
                    "**CSVファイル（ローカルCSVファイルを選択時）**\n\n"
                    "1行目に `RT`、2行目に `%Area` を先頭として各ピーク値をカンマ区切りで記載。"
                )
                st.code(
                    "RT,1.702,3.630,8.686\n"
                    "%Area,2.44,0.30,0.73",
                    language="text",
                )
                st.markdown(
                    "**OCR結果（OCR機能タブでPDFを読み取り後）**\n\n"
                    "島津・Waters 機種のHPLCレポートPDFからAzure OpenAI Vision APIで自動抽出。\n"
                    "「保持時間」または「保持時間(分)」→ RT、「面積%」または「%面積」→ %Area に変換して集計。"
                )

        # ── メインエリア（集計タブ内） ──
        if raw_data:
            # プレビューテーブル
            with st.expander("アップロードデータのプレビュー", expanded=False):
                for name, df in raw_data.items():
                    st.markdown(f"**{name}**")
                    st.dataframe(df.T, use_container_width=True)

            # RRT計算
            datasets_rrt: dict[str, pd.DataFrame] = {
                name: compute_rrt(df, main_rt_map[name])
                for name, df in raw_data.items()
            }

            # 集計テーブル構築 (キャッシュ付き)
            datasets_tuple = tuple(sorted(datasets_rrt.items()))
            result_df = build_aggregation_table(datasets_tuple, ref_name, tolerance)

            st.subheader("集計結果")
            st.dataframe(result_df, use_container_width=True)

            # CSVダウンロード
            csv_bytes = result_df.to_csv(encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="CSVダウンロード",
                data=csv_bytes,
                file_name="hplc_aggregation.csv",
                mime="text/csv",
            )
        else:
            st.info("サイドバーでデータソースを選択してデータを読み込んでください。")


if __name__ == "__main__":
    main()
