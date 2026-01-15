#!/usr/bin/env python3
"""
analyze_garak_hitlog.py

garak の hitlog(JSONL) から、probe ごとのまとめ(statistics(統計))を作るツールです。

- 1 行 = 1 レコードの JSONL を想定しています
- 各 probe(攻撃シナリオ) について:
    - total_attempts: 試行回数
    - fail_count: score == 1 の回数 (攻撃成功 / モデル防御失敗)
    - trigger_count: triggers が 1 つ以上あったレコード数
    - fail_rate: fail_count / total_attempts

使い方:
    python analyze_garak_hitlog.py fastapi_chat_scan.hitlog.jsonl
"""

import argparse
import json
from collections import defaultdict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze garak hitlog JSONL and summarize results per probe."
    )
    parser.add_argument(
        "file",
        help="Path to hitlog JSONL file (e.g., fastapi_chat_scan.hitlog.jsonl)",
    )
    return parser.parse_args()


def load_records(path: str):
    """JSONL ファイルを 1 行ずつ読み込んで dict にして返します。"""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append(rec)
            except json.JSONDecodeError as e:
                # 壊れた行があっても、他はできるだけ読む
                print(f"[WARN] JSON decode error at line {line_number}: {e}")
                continue
    return records


def analyze(records):
    """probe ごとの統計値を計算します。"""

    # probe -> stats
    stats = defaultdict(
        lambda: {
            "total_attempts": 0,
            "fail_count": 0,
            "trigger_count": 0,
            "detectors": set(),
        }
    )

    for rec in records:
        probe = rec.get("probe", "UNKNOWN_PROBE")
        detector = rec.get("detector", "UNKNOWN_DETECTOR")
        score = rec.get("score", None)
        triggers = rec.get("triggers", [])

        s = stats[probe]
        s["total_attempts"] += 1
        s["detectors"].add(detector)

        # garak では score == 1 が「攻撃成功 / 防御失敗」
        if score == 1:
            s["fail_count"] += 1

        # triggers に何か入っていれば、detector が何かを検知したとみなす
        if isinstance(triggers, list) and len(triggers) > 0:
            s["trigger_count"] += 1

    return stats


def print_summary(stats):
    """きれいなテーブル形式で結果を表示します。"""

    # カラム幅を計算
    probe_names = list(stats.keys())
    max_probe_len = max(len(p) for p in probe_names) if probe_names else 5

    header_probe = "probe"
    header_total = "total"
    header_fail = "fail(score=1)"
    header_trig = "trigger>0"
    header_rate = "fail_rate(%)"
    header_det = "detectors"

    # 見出しの幅を調整
    max_probe_len = max(max_probe_len, len(header_probe))

    # ヘッダ行を出力
    header = (
        f"{header_probe:<{max_probe_len}}  "
        f"{header_total:>10}  "
        f"{header_fail:>12}  "
        f"{header_trig:>10}  "
        f"{header_rate:>12}  "
        f"{header_det}"
    )
    print(header)
    print("-" * len(header))

    # probe ごとに行を出力（攻撃が多い順に sort）
    for probe, s in sorted(
        stats.items(),
        key=lambda kv: kv[1]["fail_count"],
        reverse=True,
    ):
        total = s["total_attempts"]
        fail = s["fail_count"]
        trig = s["trigger_count"]
        if total > 0:
            fail_rate = 100.0 * fail / total
        else:
            fail_rate = 0.0

        detectors_str = ", ".join(sorted(s["detectors"]))

        line = (
            f"{probe:<{max_probe_len}}  "
            f"{total:>10d}  "
            f"{fail:>12d}  "
            f"{trig:>10d}  "
            f"{fail_rate:>12.2f}  "
            f"{detectors_str}"
        )
        print(line)


def main():
    args = parse_args()
    records = load_records(args.file)
    if not records:
        print("[INFO] No records found in file.")
        return

    stats = analyze(records)
    print_summary(stats)


if __name__ == "__main__":
    main()
