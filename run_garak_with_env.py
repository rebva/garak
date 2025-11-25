#!/usr/bin/env python
"""
run_garak_with_env.py

Usage:
    python run_garak_with_env.py chat   # /chat をスキャン
    python run_garak_with_env.py rag    # /rag/chat をスキャン
    python run_garak_with_env.py both   # 両方
"""

import json
import os
import subprocess
import sys
from pathlib import Path  # ← これが無いと NameError になる

from dotenv import load_dotenv


# ===== .env をロード =====
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def get_env(name: str, default: str | None = None, required: bool = False) -> str:
    """環境変数(env var)を取得する helper 関数"""
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Environment variable '{name}' is required but not set.")
    return value


# ===== 共通設定 =====
API_URL = get_env("API_URL", required=True)              # 例: http://llm_api:8080
GARAK_TOKEN = get_env("GARAK_TOKEN", required=True)      # docker compose run の -e で渡す

GARAK_PROBES_CHAT = get_env(
    "GARAK_PROBES_CHAT",
    "promptinject,dan,encoding,malwaregen,packagehallucination",
)
GARAK_PROBES_RAG = get_env(
    "GARAK_PROBES_RAG",
    "promptinject,misleading,xss,leakreplay",
)

GARAK_PARALLEL_ATTEMPTS = int(get_env("GARAK_PARALLEL_ATTEMPTS", "1"))
GARAK_REQUEST_TIMEOUT = int(get_env("GARAK_REQUEST_TIMEOUT", "180"))  # 秒


def build_chat_rest_config() -> dict:
    """
    /chat 用 REST Generator 設定

    NOTE:
        response_json_field は $.reply を想定。
        FastAPI のレスポンスが {"reply": "..."} でない場合はここを変更する。
    """
    return {
        "rest": {
            "RestGenerator": {
                "name": "FastAPI Chat",
                "uri": f"{API_URL}/chat",
                "method": "post",
                "request_timeout": GARAK_REQUEST_TIMEOUT,
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GARAK_TOKEN}",
                },
                "req_template_json_object": {
                    "message": "$INPUT",  # $INPUT が garak のプロンプトに置き換わる
                    "session_id": "garak-chat-session",
                },
                "response_json": True,
                "response_json_field": "$.reply",
            }
        }
    }


def build_rag_rest_config() -> dict:
    """
    /rag/chat 用 REST Generator 設定

    NOTE:
        response_json_field は $.answer を想定。
        実際のレスポンスに合わせて変更する。
    """
    return {
        "rest": {
            "RestGenerator": {
                "name": "FastAPI RAG",
                "uri": f"{API_URL}/rag/chat",
                "method": "post",
                "request_timeout": GARAK_REQUEST_TIMEOUT,
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GARAK_TOKEN}",
                },
                "req_template_json_object": {
                    "question": "$INPUT",
                    "session_id": "garak-rag-session",
                },
                "response_json": True,
                "response_json_field": "$.answer",
            }
        }
    }


def write_config_file(config: dict, filename: str) -> Path:
    """REST generator 用 JSON 設定ファイルを書き出す"""
    path = BASE_DIR / filename
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_garak_rest(config_path: Path, probes: str, report_prefix: str) -> None:
    """
    garak CLI を REST generator 設定付きで実行する

    NOTE:
        'garak' コマンドではなく 'python -m garak' を使うことで
        PATH 問題を回避している。
    """
    args = [
        "python",
        "-m",
        "garak",
        "--target_type",
        "rest",
        "-G",
        str(config_path),
        "--probes",
        probes,
        "--parallel_attempts",
        str(GARAK_PARALLEL_ATTEMPTS),
        "--report_prefix",
        report_prefix,
    ]

    env = os.environ.copy()
    env["GARAK_TOKEN"] = GARAK_TOKEN

    print("\n=== Run garak ===")
    print("Command:", " ".join(args))
    print("API_URL:", API_URL)
    print(f"REQUEST_TIMEOUT: {GARAK_REQUEST_TIMEOUT} sec")
    print("Token:  (hidden)\n")

    result = subprocess.run(args, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"garak exited with non-zero status: {result.returncode}")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"chat", "rag", "both"}:
        print("Usage: python run_garak_with_env.py [chat|rag|both]")
        sys.exit(1)

    mode = sys.argv[1]

    if mode in {"chat", "both"}:
        print(">>> Scanning /chat endpoint...")
        chat_cfg = build_chat_rest_config()
        chat_cfg_path = write_config_file(chat_cfg, "garak_chat_rest.json")
        run_garak_rest(chat_cfg_path, GARAK_PROBES_CHAT, "fastapi_chat_scan")

    if mode in {"rag", "both"}:
        print(">>> Scanning /rag/chat endpoint...")
        rag_cfg = build_rag_rest_config()
        rag_cfg_path = write_config_file(rag_cfg, "garak_rag_rest.json")
        run_garak_rest(rag_cfg_path, GARAK_PROBES_RAG, "fastapi_rag_scan")

    print("\nAll scans finished. Check garak_runs/ and garak.log for details.")


if __name__ == "__main__":
    main()
