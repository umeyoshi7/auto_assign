import io
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st


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

    # ── サイドバー ──────────────────────────────────────────
    with st.sidebar:
        st.header("設定")

        uploaded_files = st.file_uploader(
            "CSVファイルをアップロード (最大30ファイル)",
            type=["csv"],
            accept_multiple_files=True,
        )

        if not uploaded_files:
            st.info("CSVファイルをアップロードしてください。")
            return

        if len(uploaded_files) > 30:
            st.warning("30ファイルを超えています。最初の30ファイルのみ使用します。")
            uploaded_files = uploaded_files[:30]

        # ── データ読み込み ──
        raw_data: dict[str, pd.DataFrame] = {}
        for uf in uploaded_files:
            df = parse_csv(uf.getvalue(), uf.name)
            if df is not None:
                raw_data[uf.name] = df

        if not raw_data:
            st.error("有効なCSVファイルがありません。")
            return

        st.success(f"{len(raw_data)} ファイル読み込み済み")
        st.markdown("**読み込み済みファイル:**")
        for name in raw_data:
            st.markdown(f"- {name}")

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
            # selectbox のデフォルトを %Area最大のRTに
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

    # ── メインエリア ──────────────────────────────────────────

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


if __name__ == "__main__":
    main()
