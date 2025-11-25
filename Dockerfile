FROM python:3.10

WORKDIR /app

# 1) OS パッケージのインストール（jq）
RUN apt-get update && \
    apt-get install -y jq && \
    rm -rf /var/lib/apt/lists/*

# 2) Python パッケージのインストール
#    - まず requirements.txt（garak 標準の依存関係）
#    - 追加で python-dotenv など自分用のもの
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir python-dotenv

# 3) アプリ本体のコピー
COPY . /app

# 4) デフォルトは待機（スキャンは docker compose run で実行）
CMD ["sleep", "infinity"]
