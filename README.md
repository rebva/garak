
---

# ローカル拡張メモ：FastAPI LLM 用 garak スキャナ環境

このディレクトリは本来 **NVIDIA/garak** のソース一式ですが、
その上に **自前の FastAPI LLM & RAG サーバをスキャンするための Docker 実行環境** を追加しています。

将来の自分が「この Dockerfile 何？」となったときのために、
**自分で追加／編集したファイル** と用途をここにまとめておきます。

---

## 1. 自分が追加・編集したファイル一覧

### ✅ 追加・編集したファイル

* `Dockerfile`

  * ベースイメージ: `python:3.10`
  * やっていること：

    * `WORKDIR /app`
    * `requirements.txt` をインストール
    * `python-dotenv` も追加インストール
    * 全ソースを `/app` にコピー
    * `jq` を apt でインストール（コンテナ内で `curl | jq` がしたかったため）
  * 目的：

    * **garak をコンテナ内で完結して動かす専用イメージ**を作る

* `docker-compose.yaml`

  * サービス名: `garak`
  * イメージ: 上記 Dockerfile からビルドした `garak-garak`
  * 主な設定：

    ```yaml
    services:
      garak:
        build: .
        container_name: garak_scanner
        environment:
          - API_URL=http://llm_api:8080
          - GARAK_USERNAME=user1
          - GARAK_PASSWORD=user1
          - GARAK_PROBES_CHAT=promptinject
          - GARAK_PROBES_RAG=promptinject
          - GARAK_PARALLEL_ATTEMPTS=1
          - GARAK_REQUEST_TIMEOUT=180
        networks:
          - garak-net

    networks:
      garak-net:
        external: true
    ```
  * ポイント：

    * `API_URL` は **LLM FastAPI コンテナ**（`llm_api`）を指す
    * `garak-net` は **外部ネットワーク**（`docker network create garak-net`）を前提
    * garak コンテナと LLM コンテナを同じネットワークに入れて **内部通信**させる

* `.env`

  * `run_garak_with_env.py` が読む設定ファイル
  * 例：

    ```env
    API_URL=http://llm_api:8080

    GARAK_USERNAME=user1
    GARAK_PASSWORD=user1

    GARAK_PROBES_CHAT=promptinject
    GARAK_PROBES_RAG=promptinject

    GARAK_PARALLEL_ATTEMPTS=1
    GARAK_REQUEST_TIMEOUT=180
    ```
  * 必要に応じてここでプローブやタイムアウトを変更する

* `requirements.txt`

  * もともとの NVIDIA/garak の内容に加えて、

    * `python-dotenv`
    * （必要なら）`requests`
  * を追加している。
  * 目的：

    * `run_garak_with_env.py` で `.env` を扱うため
    * FastAPI の `/login` を叩いて JWT を取るため

* `run_garak_with_env.py`

  * **今回のカスタム実行スクリプトの本体**
  * 役割：

    1. `.env` をロード
    2. `API_URL`, `GARAK_USERNAME`, `GARAK_PASSWORD` などを取得
    3. `requests` を使って `POST {API_URL}/login` を叩き、JWT (`access_token`) を取得
    4. その JWT を `Authorization: Bearer ...` に入れた REST Generator 用コンフィグ

       * `/chat` 用 → `garak_chat_rest.json`
       * `/rag/chat` 用 → `garak_rag_rest.json`
         を動的に生成
    5. `python -m garak --target_type rest ...` を subprocess で実行
  * 使い方（コンテナ内）：

    ```bash
    python run_garak_with_env.py chat   # /chat エンドポイントだけスキャン
    python run_garak_with_env.py rag    # /rag/chat だけスキャン
    python run_garak_with_env.py both   # 両方
    ```

* `garak_chat_rest.json` / `garak_rag_rest.json`

  * **自動生成される REST Generator 設定**
  * `run_garak_with_env.py` 実行時に書き出される
  * 手で編集する必要は基本的に無い（壊したらまたスクリプトが上書きしてくれる）

---

## 2. 想定している全体構成

この garak ディレクトリ単体では **スキャナ側** だけを提供している。
想定している構成は次の 3 コンテナ構成：

* `ollama_rebva`

  * Ollama サーバ（ローカル LLM 実行）
* `llm_api`

  * FastAPI ベースの LLM & RAG API
  * エンドポイント：

    * `POST /login` → JWT 発行
    * `POST /chat` → 通常チャット
    * `POST /rag/chat` → RAG チャット
* `garak_scanner`（このリポジトリの Dockerfile からビルド）

  * garak CLI を使って `llm_api` を叩き、脆弱性診断を行う
  * 通信は `garak-net` ネットワーク上で `http://llm_api:8080` に向けて実施

---

## 3. よく使うコマンド（自分用チートシート）

### 3-1. 初回セットアップ

```bash
# garak 側リポジトリに移動
cd ~/docker/garak_env/garak

# Docker ネットワーク作成（まだ無い場合）
docker network create garak-net

# FastAPI 側コンテナ(llm_api) を garak-net に参加させる（compose 側で設定しておく）
# 例: llmapi 側 docker-compose.yaml に
#   networks:
#     - garak-net
# を追加して up する。
```

### 3-2. garak イメージのビルド

```bash
cd ~/docker/garak_env/garak
docker compose build
```

### 3-3. `/chat` に対して prompt injection だけ試す

`.env` または `docker-compose.yaml` に

```env
GARAK_PROBES_CHAT=promptinject
```

が入っている状態で：

```bash
docker compose run --rm garak python run_garak_with_env.py chat
```

* コンテナ内部で `/login` → JWT 取得
* `garak_chat_rest.json` を生成
* `python -m garak --target_type rest ...` で `promptinject.*` を実行
* レポート：

  * `/root/.local/share/garak/garak_runs/*.report.jsonl`
  * `/root/.local/share/garak/garak.log`

レポートをホストから見たい場合は、`docker-compose.yaml` の `volumes` を有効化する：

```yaml
    volumes:
      - ./garak_runs:/root/.local/share/garak/garak_runs
```

---

## 4. 注意点・ハマりがちなポイント

* **401 Unauthorized で落ちる場合**

  * 以前は「ホストで JWT を取って `GARAK_TOKEN` で渡す方式」でよく 401 が出ていた
  * 現行設計では `run_garak_with_env.py` が **コンテナ内から直接 `/login`** するようにしているので、
    `.env` の `GARAK_USERNAME` / `GARAK_PASSWORD` が FastAPI 側と一致しているかを確認すれば OK

* **`garak/garak` ディレクトリが二重に見える問題**

  * 外側の `garak` … リポジトリルート
  * 内側の `garak` … Python パッケージ (`python -m garak` の実体)
  * 一見キモいが、Python界隈ではよくある構成なので気にしなくてよい

* **ディスクがパンパン問題**

  * 画像系コンテナ（Matlab, freesurfer など）で `/` が満杯になりやすい
  * 時々 `docker system df` / `docker image rm` / `docker volume rm` でお掃除すること

---

## 5. 将来の拡張メモ

* `GARAK_PROBES_CHAT` / `GARAK_PROBES_RAG` にカンマ区切りで増やすだけで、
  他の probe（`malwaregen`, `encoding` など）も追加可能。
* RAG 向けに

  * `leakreplay`
  * `misleading`
  * `xss`
    などを有効化して、RAG 特有の情報漏洩やプロンプトインジェクションを重点的にテストすることもできる。

---

