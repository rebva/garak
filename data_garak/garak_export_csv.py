#!/usr/bin/env python3
"""
Convert garak JSONL reports into human-friendly CSV files.

- report.jsonl -> garak_report_summary.csv
- hitlog.jsonl -> garak_hitlog_details.csv

Usage:
    python garak_export_csv.py fastapi_chat_scan.report.jsonl fastapi_chat_scan.hitlog.jsonl
"""

import sys
import json
import csv
from collections import defaultdict
from pathlib import Path


def load_jsonl(path: Path):
    """Read a JSONL (JSON Lines) file line by line.

    JSONL: 1 line = 1 JSON object
    """
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # If line is broken, just skip it (安全のため)
                continue


def export_report_summary(report_path: Path, output_path: Path):
    """
    Summarize garak report JSONL by (probe, detector).

    Output CSV columns:
        probe, detector, n_rows, n_with_score, avg_score
    """
    # (probe, detector) -> list of scores
    scores_by_key = defaultdict(list)
    count_by_key = defaultdict(int)

    for row in load_jsonl(report_path):
        probe = row.get("probe")
        detector = row.get("detector")
        score = row.get("score")

        # Skip rows without probe (メタ情報など)
        if probe is None:
            continue

        key = (probe, detector)
        count_by_key[key] += 1

        # score が数値なら集計対象
        if isinstance(score, (int, float)):
            scores_by_key[key].append(float(score))

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["probe", "detector", "n_rows", "n_with_score", "avg_score"])

        for (probe, detector), n_rows in sorted(count_by_key.items()):
            score_list = scores_by_key.get((probe, detector), [])
            n_with_score = len(score_list)
            avg_score = sum(score_list) / n_with_score if n_with_score > 0 else ""
            writer.writerow([probe, detector, n_rows, n_with_score, avg_score])

    print(f"[OK] report summary -> {output_path}")


def export_hitlog_details(hitlog_path: Path, output_path: Path):
    """
    Extract useful fields from hitlog JSONL.

    Output CSV columns:
        probe, detector, score, goal, trigger, prompt, output
    """
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["probe", "detector", "score", "goal",
                         "trigger", "prompt", "output"])

        for row in load_jsonl(hitlog_path):
            probe = row.get("probe")
            detector = row.get("detector")
            score = row.get("score")
            goal = row.get("goal")
            trigger = row.get("trigger")
            prompt = row.get("prompt")
            output_text = row.get("output")

            # probe が無い行はスキップ（メタ情報など）
            if probe is None:
                continue

            writer.writerow([
                probe,
                detector,
                score,
                goal,
                trigger,
                # CSV なので、改行多い prompt / output はそのまま入れて OK
                prompt,
                output_text,
            ])

    print(f"[OK] hitlog details -> {output_path}")


def main():
    if len(sys.argv) != 3:
        print("Usage:")
        print("  python garak_export_csv.py fastapi_chat_scan.report.jsonl fastapi_chat_scan.hitlog.jsonl")
        sys.exit(1)

    report_path = Path(sys.argv[1])
    hitlog_path = Path(sys.argv[2])

    if not report_path.exists():
        print(f"[ERROR] report file not found: {report_path}")
        sys.exit(1)

    if not hitlog_path.exists():
        print(f"[ERROR] hitlog file not found: {hitlog_path}")
        sys.exit(1)

    export_report_summary(report_path, Path("garak_report_summary.csv"))
    export_hitlog_details(hitlog_path, Path("garak_hitlog_details.csv"))


if __name__ == "__main__":
    main()
