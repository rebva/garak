
---

````markdown
# FastAPI LLM 用 garak スキャナ拡張メモ

このディレクトリは本来 **NVIDIA/garak** のソース一式ですが、  
その上に **自前 FastAPI LLM & RAG サーバをスキャンするための Docker 実行環境** を後付けしています。

将来の自分が

> 「この Dockerfile 何？この run_garak_with_env.py 誰？」

と首をかしげないように、  
**自分で追加・変更したファイル / 役割 / 使い方** をここにまとめておきます。

---

## 1. 自分が追加・編集したファイル一覧

### 1-1. `Dockerfile`

ベースイメージ: `python:3.10`

やっていること:

- `WORKDIR /app`
- `apt-get` で `jq` をインストール  
  → コンテナ内で `curl ... | jq` ができるようにしただけ
- `requirements.txt` をコピーして `pip install`
- 追加で `python-dotenv` をインストール
- カレントディレクトリ全体を `/app` にコピー
- デフォルト CMD は `sleep infinity`（コンテナ起動後に手動でコマンドを叩くスタイル）

目的:

- **garak をコンテナ内で完結して動かすための専用イメージ**を作る

---

### 1-2. `docker-compose.yaml`

サービス定義（抜粋）:

```yaml
version: "3.9"

services:
  garak:
    build: .
    container_name: garak_scanner
    environment:
      - API_URL=http://llm_api:8080

      # どの probe(攻撃パターン) を使うか
      - GARAK_PROBES_CHAT=promptinject
      - GARAK_PROBES_RAG=promptinject

      # 並列数・タイムアウト
      - GARAK_PARALLEL_ATTEMPTS=1
      - GARAK_REQUEST_TIMEOUT=180
      # GARAK_TOKEN はここにベタ書きしない。実行時に -e で渡す。

    networks:
      - garak-net

networks:
  garak-net:
    external: true
````

ポイント:

* `API_URL` は **FastAPI LLM コンテナのサービス名 + ポート**

  * 例: LLM 側 compose が `container_name: llm_api` / `ports: "8080:8080"` なら
    `http://llm_api:8080` で OK
* `garak-net` は **外部 Docker ネットワーク**
  → 事前に `docker network create garak-net` しておくこと
* **認証系の情報（ユーザー名 / パスワード / トークン）はここに書かない**

  * ユーザー名・パスワード → `.env` で管理
  * JWT トークン → 実行時に `/login` を叩いて動的に取得（あとで説明）

---

### 1-3. `.env`

`run_garak_with_env.py` が読み込む設定ファイル。

例:

```env
API_URL=http://llm_api:8080

# garak が FastAPI /login で使うアカウント
GARAK_USERNAME=user1
GARAK_PASSWORD=user1

# プロンプトインジェクションだけ試したい
GARAK_PROBES_CHAT=promptinject
GARAK_PROBES_RAG=promptinject

GARAK_PARALLEL_ATTEMPTS=1
GARAK_REQUEST_TIMEOUT=180
```

ポイント:

* **ユーザー名 / パスワードは `.env` にのみ記載**（compose の environment には書かない）
* `run_garak_with_env.py` は起動時に `.env` をロードし、ここから値を読む
* プローブの種類やタイムアウトもここで変更可能

---

### 1-4. `requirements.txt`

もともとの `NVIDIA/garak` の `requirements.txt` に加えて、最低限次を追加:

* `python-dotenv` : `.env` を読むため
* `requests` : FastAPI の `/login` に HTTP リクエストするため

（実際に何を足したかは `git diff` で確認できる）

---

### 1-5. `run_garak_with_env.py`

今回の **カスタム実行スクリプトの本体**。

#### 役割（ざっくり）

1. `.env` をロード
2. `API_URL`, `GARAK_USERNAME`, `GARAK_PASSWORD` などを環境変数から取得
3. `requests.post(API_URL + "/login")` でログインし、JWT (`access_token`) を取得
4. 取得した JWT を `Authorization: Bearer <token>` として使う REST Generator 用設定を生成

   * `/chat` 用 → `garak_chat_rest.json`
   * `/rag/chat` 用 → `garak_rag_rest.json`
5. 最後に `python -m garak --target_type rest ...` を `subprocess.run` で実行

#### 起動方法（コンテナ内）

```bash
python run_garak_with_env.py chat   # /chat エンドポイントだけスキャン
python run_garak_with_env.py rag    # /rag/chat だけスキャン
python run_garak_with_env.py both   # 両方まとめて
```

引数チェック:

* 引数が `chat | rag | both` 以外の場合は Usage を表示して終了するようにしてある

---

### 1-6. `garak_chat_rest.json` / `garak_rag_rest.json`

* どちらも **`run_garak_with_env.py` 実行時に自動生成される**。
* 基本的には **手で編集しない想定**。

  * 壊しても再度 `run_garak_with_env.py` を叩けば上書きされる。

中身としては、どちらも形式はほぼ同じで、

* `uri` が `/chat` か `/rag/chat` かの違い
* `req_template_json_object` のキーが違う

  * `/chat` : `{"message": "$INPUT", "session_id": "garak-chat-session"}`
  * `/rag/chat` : `{"question": "$INPUT", "session_id": "garak-rag-session"}`

という程度の差。

---

## 2. 想定している全体構成

この garak リポジトリは **スキャナ側** だけ。

想定する全体像（ざっくり 3 コンテナ構成）は次の通り：

1. **Ollama サーバ**

   * 例: `container_name: ollama_rebva`
   * `llama3` などのローカル LLM を提供

2. **FastAPI LLM API**

   * 例: `container_name: llm_api`
   * 主なエンドポイント:

     * `POST /login` → JWT 発行
     * `POST /chat` → 通常チャット
     * `POST /rag/chat` → RAG チャット

3. **garak スキャナ（このイメージ）**

   * `container_name: garak_scanner`
   * `python -m garak --target_type rest ...` で 2. の API に対して脆弱性診断を実施
   * 通信は共通ネットワーク `garak-net` 経由で `http://llm_api:8080` に向けて行う

---

## 3. よく使うコマンド（自分用チートシート）

### 3-1. 初回セットアップ

```bash
# garak リポジトリに移動
cd ~/docker/garak_env/garak

# 共通ネットワーク作成（まだ無ければ）
docker network create garak-net
```

> ※ FastAPI 側 compose でも `networks: [garak-net]` を指定しておくこと。
> そうしないと `llm_api` と `garak_scanner` が同じ L2 に乗らない。

---

### 3-2. garak イメージのビルド

```bash
cd ~/docker/garak_env/garak
docker compose build
```

---

### 3-3. `/chat` に対して prompt injection だけ試す

`.env` が次のようになっている前提:

```env
GARAK_PROBES_CHAT=promptinject
GARAK_PROBES_RAG=promptinject
```

実行:

```bash
docker compose run --rm garak python run_garak_with_env.py chat
```

* コンテナ内部から `POST ${API_URL}/login` を叩き、
  `GARAK_USERNAME` / `GARAK_PASSWORD` でログイン
* 返ってきた JWT を使って `garak_chat_rest.json` を生成
* その設定で `python -m garak --target_type rest ...` を実行

レポートの保存先（デフォルト）:

* `/root/.local/share/garak/garak_runs/*.report.jsonl`
* `/root/.local/share/garak/garak.log`

ホスト側からレポートを見たい場合は、`docker-compose.yaml` の `volumes` を有効化する:

```yaml
    volumes:
      - ./garak_runs:/root/.local/share/garak/garak_runs
```

---

### 3-4. `/rag/chat` も含めて両方まとめてスキャンする

```bash
docker compose run --rm garak python run_garak_with_env.py both
```

---

## 4. 注意点・トラブルシュートメモ

### 4-1. 401 Unauthorized が出る場合

考えられる原因:

1. `.env` の `GARAK_USERNAME` / `GARAK_PASSWORD` と
   FastAPI 側のユーザー情報が一致していない
2. `API_URL` が FastAPI コンテナを指していない
   （例: `llm_api` ではなく `localhost:8080` などになっている）

チェックポイント:

* コンテナ内で直接 `curl`:

  ```bash
  docker compose run --rm garak bash

  # コンテナの中で
  curl -s -X POST "$API_URL/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"user1","password":"user1"}'
  ```

* ここで正常に JWT が返るなら、`run_garak_with_env.py` 側のバグよりも
  認証情報・URL 設定の問題である可能性が高い。

---

### 4-2. GARAK_TOKEN をどうするか

今回は **毎回 /login して JWT を取得する方式** を採用しているため、
`GARAK_TOKEN` 環境変数は **必須ではない**。

もしも別の認証方式で

* 「事前に発行しておいた固定トークンを使いたい」

という構成に変える場合は、

* `.env` に `GARAK_TOKEN=` を追加
* `run_garak_with_env.py` で `fetch_jwt_token()` の代わりに `os.getenv("GARAK_TOKEN")` を使う
  …という形に変更する。

---

### 4-3. garak のレポートでディスクが膨らむ問題

garak は走らせる度に `garak_runs` にレポートファイルを貯めていく。
テストを大量に回すと、地味にディスクを圧迫するので、たまに掃除する:

```bash
# ホスト側で
cd ~/docker/garak_env/garak
rm -rf garak_runs/*
```

※ もちろん `docker system prune` 等で他のコンテナや volume ごと掃除するのもアリ。

---

## 5. 将来の拡張メモ

* `GARAK_PROBES_CHAT` / `GARAK_PROBES_RAG` に
  カンマ区切りで probe 名を足すだけで攻撃パターンを増やせる

  例:

  ```env
  GARAK_PROBES_CHAT=promptinject,dan,encoding,malwaregen,packagehallucination
  GARAK_PROBES_RAG=promptinject,misleading,xss,leakreplay
  ```

* RAG 特有の検査に強くしたい場合は

  * `leakreplay` : 過去会話やコンテンツの再漏洩検査
  * `misleading` : 誤誘導（ミスリード）系
  * `xss` : 出力をそのまま Web に出した場合の XSS リスク

  を重点的に有効化すると良い。

---

