#!/usr/bin/env python3
"""
Convert garak JSONL reports into human-friendly CSV files.

- report.jsonl -> garak_report_summary.csv        (simple summary)
- hitlog.jsonl -> garak_hitlog_details.csv       (raw hitlog fields)
- report.jsonl -> garak_attempts_flat.csv        (FLATTENED attempts: prompt/output)

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


# ----------------------------------------------------------------------
# 1) report.jsonl -> simple summary (旧ロジック + probe_classname 対応)
# ----------------------------------------------------------------------
def export_report_summary(report_path: Path, output_path: Path):
    """
    Summarize garak report JSONL by (probe, detector).

    Output CSV columns:
        probe, detector, n_rows, n_with_score, avg_score

    - 古いフォーマット: row["probe"], row["detector"], row["score"]
    - 今回のような attempt フォーマットでは score が無いことが多いので、
      「集計結果が薄い」こともあります（その場合は attempts_flat を見る）。
    """
    scores_by_key = defaultdict(list)
    count_by_key = defaultdict(int)

    for row in load_jsonl(report_path):
        # まず "probe" があればそれを優先（古い / hitlog 互換）
        probe = row.get("probe")
        detector = row.get("detector")
        score = row.get("score")

        # 無い場合は attempt 形式を軽く見る（probe_classname / detector_results）
        if probe is None and row.get("entry_type") == "attempt":
            probe = row.get("probe_classname")
            # detector_results: {detector_name: {...}} だが、
            # ここでは「ざっくり代表一つ」でまとめる
            det_results = row.get("detector_results") or {}
            detector = ",".join(sorted(det_results.keys())) if det_results else None
            # score は detector_results の中にある場合があるが、
            # ここでは複雑なので集計しない（attempts_flat側で詳細を確認する）

        # probe が無い行はスキップ（メタ情報や init など）
        if probe is None:
            continue

        key = (probe, detector)
        count_by_key[key] += 1

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


# ----------------------------------------------------------------------
# 2) hitlog.jsonl -> 詳細 (既存ロジックそのまま)
# ----------------------------------------------------------------------
def export_hitlog_details(hitlog_path: Path, output_path: Path):
    """
    Extract useful fields from hitlog JSONL.

    Output CSV columns:
        probe, detector, score, goal, trigger, prompt, output

    ※ hitlog 側にあまり情報が無い場合は、ここがスカスカになることもあります。
      その場合は attempts_flat の方がメインになります。
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
                prompt,
                output_text,
            ])

    print(f"[OK] hitlog details -> {output_path}")


# ----------------------------------------------------------------------
# 3) report.jsonl -> FLATTENED attempts
# ----------------------------------------------------------------------
def flatten_attempt_row(row: dict) -> dict:
    """
    Garak report の "entry_type == attempt" をフラットな dict にする。

    出力フィールド:
        entry_type, run_id, seq, status,
        probe_classname, goal,
        triggers,  ( "|" で join した文字列)
        prompt_text,  (全 user プロンプトを結合)
        outputs_text  (全 generations を結合)
    """
    entry_type = row.get("entry_type")
    if entry_type != "attempt":
        return {}

    run_id = row.get("run") or row.get("run_id") or ""
    seq = row.get("seq")
    status = row.get("status")

    probe_classname = row.get("probe_classname") or ""
    goal = row.get("goal") or ""

    # triggers: list ->  " | " で join
    triggers_list = row.get("triggers") or []
    if isinstance(triggers_list, list):
        triggers_text = " | ".join(str(t) for t in triggers_list)
    else:
        triggers_text = str(triggers_list)

    # prompt: { "turns": [ { "role": "...", "content": { "text": "..." } }, ... ] }
    prompt = row.get("prompt") or {}
    turns = prompt.get("turns") or []
    prompt_texts = []
    for t in turns:
        content = (t or {}).get("content") or {}
        text = content.get("text")
        if isinstance(text, str):
            prompt_texts.append(text)
    prompt_text = "\n---\n".join(prompt_texts)

    # outputs: [ { "text": "..." }, ... ]
    outputs = row.get("outputs") or []
    output_texts = []
    for o in outputs:
        text = (o or {}).get("text")
        if isinstance(text, str):
            output_texts.append(text)
    # generations を " \n====\n " で区切ってまとめる
    outputs_text = "\n====\n".join(output_texts)

    return {
        "entry_type": entry_type,
        "run_id": run_id,
        "seq": seq,
        "status": status,
        "probe_classname": probe_classname,
        "goal": goal,
        "triggers": triggers_text,
        "prompt_text": prompt_text,
        "outputs_text": outputs_text,
    }


def export_attempts_flat(report_path: Path, output_path: Path):
    """
    report.jsonl から "attempt" エントリをフラットな CSV にする。

    Output CSV columns:
        entry_type, run_id, seq, status,
        probe_classname, goal, triggers,
        prompt_text, outputs_text
    """
    rows = []

    for row in load_jsonl(report_path):
        flat = flatten_attempt_row(row)
        if not flat:
            continue
        rows.append(flat)

    if not rows:
        print("[WARN] no attempt entries found in report.jsonl")
        return

    fieldnames = [
        "entry_type",
        "run_id",
        "seq",
        "status",
        "probe_classname",
        "goal",
        "triggers",
        "prompt_text",
        "outputs_text",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"[OK] attempts flat -> {output_path}")


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
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
    export_attempts_flat(report_path, Path("garak_attempts_flat.csv"))


if __name__ == "__main__":
    main()
