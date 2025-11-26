#!/usr/bin/env bash
set -euo pipefail

#############################################
# 1) ここで「使いたい promptinject probe」を指定
#    まずは `--list_probes -p promptinject` の結果から
#    実在する名前をコピペしてください
#############################################
PROMPTINJECT_PROBE="${PROMPTINJECT_PROBE:-promptinject}"  
# 例:
PROMPTINJECT_PROBE="leakreplay"
# PROMPTINJECT_PROBE="promptinject.HijackLongPrompt"
# PROMPTINJECT_PROBE="promptinject.AttackRogueString"

#############################################
# 2) LLM API / アカウント情報
#############################################

# ホストから見た LLM API
HOST_LLM_URL="${HOST_LLM_URL:-http://localhost:8080}"

# ログイン用ユーザー
GARAK_USER="${GARAK_USERNAME:-user1}"
GARAK_PASS="${GARAK_PASSWORD:-user1}"

# garak コンテナ内から見た LLM API
GARAK_API_URL_IN_DOCKER="${API_URL:-http://llm_api:8080}"

echo "== [1] Get JWT token from LLM API =="
echo "  -> POST ${HOST_LLM_URL}/login (user: ${GARAK_USER})"

TOKEN="$(
  curl -sS -X POST "${HOST_LLM_URL}/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${GARAK_USER}\",\"password\":\"${GARAK_PASS}\"}" \
    | jq -r '.access_token'
)"

if [ -z "${TOKEN}" ] || [ "${TOKEN}" = "null" ]; then
  echo "!!! Failed to get token. Check /login API or credentials." >&2
  exit 1
fi

echo "  -> OK, got token (length: ${#TOKEN})"


echo
echo "== [2] Run garak with ONE promptinject probe =="
echo "  -> Target in Docker: ${GARAK_API_URL_IN_DOCKER}/chat"
echo "  -> Probe: ${PROMPTINJECT_PROBE}"

docker compose run --rm \
  -e GARAK_TOKEN="${TOKEN}" \
  -e API_URL="${GARAK_API_URL_IN_DOCKER}" \
  -e GARAK_PROBES_CHAT="${PROMPTINJECT_PROBE}" \
  -e GARAK_PARALLEL_ATTEMPTS="${GARAK_PARALLEL_ATTEMPTS:-1}" \
  -e GARAK_REQUEST_TIMEOUT="${GARAK_REQUEST_TIMEOUT:-180}" \
  garak \
  python run_garak_with_env.py chat

echo
echo "== [DONE] Single promptinject probe scan finished =="
