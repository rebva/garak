#!/usr/bin/env python3
"""
Convert garak JSONL reports into human-friendly CSV files.

- report.jsonl -> garak_report_summary.csv
- hitlog.jsonl -> garak_hitlog_details.csv
- report.jsonl -> garak_attempts_flat.csv   ★ 各 attempt をフラット化した「完全版」

Usage:
    python garak_export_csv.py fastapi_chat_scan.report.jsonl fastapi_chat_scan.hitlog.jsonl
"""

import sys
import json
import csv
from collections import defaultdict
from pathlib import Path


def load_jsonl(path: Path):
    """JSONL (JSON Lines) を1行ずつ読むジェネレータ."""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # 壊れた行はスキップ（安全優先）
                continue


# ------------------------------------------------------------
# 1) サマリ: (probe, detector) ごとのスコア集計
# ------------------------------------------------------------
def export_report_summary(report_path: Path, output_path: Path):
    """
    Summarize garak report JSONL by (probe, detector).

    Output CSV columns:
        probe, detector, n_rows, n_with_score, avg_score
    """
    scores_by_key = defaultdict(list)  # (probe, detector) -> [scores...]
    count_by_key = defaultdict(int)

    for row in load_jsonl(report_path):
        probe = row.get("probe")
        detector = row.get("detector")
        score = row.get("score")

        # probe がない行はメタ情報なので無視
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


# ------------------------------------------------------------
# 2) hitlog: (probe, detector, score, goal, trigger, prompt, output)
#    ※ 現状 hitlog 側には中身があまり無いケースもある
# ------------------------------------------------------------
def export_hitlog_details(hitlog_path: Path, output_path: Path):
    """
    Extract useful fields from hitlog JSONL.

    Output CSV columns:
        probe, detector, score, goal, trigger, prompt, output
    """
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["probe", "detector", "score", "goal", "trigger", "prompt", "output"]
        )

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

            writer.writerow(
                [
                    probe,
                    detector,
                    score,
                    goal,
                    trigger,
                    prompt,
                    output_text,
                ]
            )

    print(f"[OK] hitlog details -> {output_path}")


# ------------------------------------------------------------
# 3) 完全版フラットナー: report.jsonl の "attempt" を 1行1レコードにする
# ------------------------------------------------------------
def export_attempts_flat(report_path: Path, output_path: Path):
    """
    Flatten "attempt" entries from report JSONL.

    Output CSV columns (例):
        run_id, attempt_seq, attempt_uuid,
        probe_classname, goal, triggers,
        prompt_text, outputs_text

    - prompt_text  : prompt.turns[*].content.text を結合
    - outputs_text : outputs[*].text を区切りつきで結合
    """
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        writer.writerow(
            [
                "run_id",
                "attempt_seq",
                "attempt_uuid",
                "probe_classname",
                "goal",
                "triggers",
                "prompt_text",
                "outputs_text",
            ]
        )

        for row in load_jsonl(report_path):
            # "attempt" 以外（init, setup など）は無視
            if row.get("entry_type") != "attempt":
                continue

            run_id = row.get("run_id") or row.get("run")  # どちらか入っている想定
            attempt_seq = row.get("seq")
            attempt_uuid = row.get("uuid")
            probe_classname = row.get("probe_classname")
            goal = row.get("goal")

            # triggers: list -> " | " で結合
            triggers_list = row.get("triggers") or []
            if isinstance(triggers_list, list):
                triggers = " | ".join(str(t) for t in triggers_list)
            else:
                triggers = str(triggers_list) if triggers_list is not None else ""

            # prompt_text の抽出
            prompt_obj = row.get("prompt") or {}
            prompt_turns = prompt_obj.get("turns") or []
            prompt_texts = []
            for t in prompt_turns:
                content = t.get("content") or {}
                text = content.get("text")
                if text:
                    prompt_texts.append(text)
            prompt_text = "\n\n---\n\n".join(prompt_texts)

            # outputs_text の抽出
            outputs = row.get("outputs") or []
            outputs_texts = []
            for i, out in enumerate(outputs):
                if not isinstance(out, dict):
                    continue
                text = out.get("text")
                if not text:
                    continue
                # どの出力か分かるように軽くヘッダを付ける
                outputs_texts.append(f"[OUTPUT {i}]\n{text}")
            outputs_text = "\n\n====\n\n".join(outputs_texts)

            writer.writerow(
                [
                    run_id,
                    attempt_seq,
                    attempt_uuid,
                    probe_classname,
                    goal,
                    triggers,
                    prompt_text,
                    outputs_text,
                ]
            )

    print(f"[OK] attempts flat -> {output_path}")


# ------------------------------------------------------------
# main
# ------------------------------------------------------------
def main():
    if len(sys.argv) != 3:
        print("Usage:")
        print(
            "  python garak_export_csv.py fastapi_chat_scan.report.jsonl fastapi_chat_scan.hitlog.jsonl"
        )
        sys.exit(1)

    report_path = Path(sys.argv[1])
    hitlog_path = Path(sys.argv[2])

    if not report_path.exists():
        print(f"[ERROR] report file not found: {report_path}")
        sys.exit(1)

    if not hitlog_path.exists():
        print(f"[ERROR] hitlog file not found: {hitlog_path}")
        sys.exit(1)

    # ① (probe, detector) のスコアサマリ
    export_report_summary(report_path, Path("garak_report_summary.csv"))

    # ② hitlog から軽い情報を抽出
    export_hitlog_details(hitlog_path, Path("garak_hitlog_details.csv"))

    # ③ report.jsonl の attempt をフラットに展開（★本命）
    export_attempts_flat(report_path, Path("garak_attempts_flat.csv"))


if __name__ == "__main__":
    main()
