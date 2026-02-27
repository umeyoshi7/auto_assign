"""
generate_test_data.py
HPLCチャート風のCSVテストデータを10ファイル生成する。
"""

import os
import random
import numpy as np

random.seed(42)
np.random.seed(42)

OUTPUT_DIR = "test_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 骨格ピーク群: (RT_base, label) — 全サンプル共通の「基本ピーク」
SKELETON_PEAKS = [
    0.72,   # 前駆不純物A
    1.05,   # 前駆不純物B
    2.18,   # 不純物C
    5.40,   # 不純物D
    10.00,  # ← メインピーク (index=5 を想定)
    13.60,  # 不純物E
    18.20,  # 不純物F
    22.50,  # 不純物G
    26.30,  # 不純物H
]
MAIN_PEAK_IDX = 4  # SKELETON_PEAKS[4] = 10.00 がメインピーク

# 骨格外ピーク候補
EXTRA_PEAKS = [3.10, 7.80, 11.40, 15.70, 19.90, 24.10, 28.60]


def generate_sample(sample_id: int) -> tuple[list[float], list[float]]:
    """
    1サンプル分の (RT リスト, %Area リスト) を生成する。
    - 骨格ピークに ±RT_JITTER の変動を加える
    - 一部の骨格ピークをランダムに削除
    - 骨格外ピークをランダムに追加
    - メインピークのRTは 10〜20 の範囲でランダム (±3%)
    - 全%Area合計=100% に正規化
    """
    RT_JITTER = 0.02  # ±2% 程度
    peaks = []  # [(rt, area_raw), ...]

    # メインピークのベースRTをサンプルごとにランダム化 (10〜20)
    main_rt_base = random.uniform(10.0, 20.0)
    scale = main_rt_base / SKELETON_PEAKS[MAIN_PEAK_IDX]  # スケール係数

    for idx, rt_base in enumerate(SKELETON_PEAKS):
        # ランダムに一部骨格ピークを削除 (メインピークは必須)
        if idx != MAIN_PEAK_IDX and random.random() < 0.25:
            continue

        rt = rt_base * scale * (1.0 + random.uniform(-RT_JITTER, RT_JITTER))
        if idx == MAIN_PEAK_IDX:
            area_raw = random.uniform(85.0, 95.0)
        else:
            area_raw = random.uniform(0.01, 3.0)
        peaks.append((rt, area_raw))

    # 骨格外ピークをランダムに追加 (0〜4個)
    n_extra = random.randint(0, 4)
    extra_chosen = random.sample(EXTRA_PEAKS, min(n_extra, len(EXTRA_PEAKS)))
    for rt_base in extra_chosen:
        rt = rt_base * scale * (1.0 + random.uniform(-RT_JITTER, RT_JITTER))
        area_raw = random.uniform(0.01, 2.0)
        peaks.append((rt, area_raw))

    # RTでソート
    peaks.sort(key=lambda x: x[0])

    # %Area 合計100に正規化
    total_area = sum(a for _, a in peaks)
    rts = [round(rt, 3) for rt, _ in peaks]
    areas = [round(a / total_area * 100.0, 4) for _, a in peaks]

    return rts, areas


def write_csv(filepath: str, rts: list[float], areas: list[float]):
    rt_row = "RT," + ",".join(str(v) for v in rts)
    area_row = "%Area," + ",".join(str(v) for v in areas)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(rt_row + "\n")
        f.write(area_row + "\n")
    print(f"  Written: {filepath}  ({len(rts)} peaks)")


def main():
    print(f"Generating test data in '{OUTPUT_DIR}/'...")
    for i in range(1, 11):
        filename = f"sample_{i:02d}.csv"
        filepath = os.path.join(OUTPUT_DIR, filename)
        rts, areas = generate_sample(i)
        write_csv(filepath, rts, areas)
    print("Done.")


if __name__ == "__main__":
    main()
