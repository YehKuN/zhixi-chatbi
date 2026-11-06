#!/bin/sh
# DataLink 独立服务启动；图谱库与数据源目录与主后端共用同一存储根。
set -eu

if [ -n "${CHATBI_STORAGE_ROOT:-}" ]; then
    export DATALINK_SOURCE_ROOT="$CHATBI_STORAGE_ROOT/datasources"
    export DATALINK_DATABASE_PATH="$CHATBI_STORAGE_ROOT/datalink/datalink.db"
fi

mkdir -p \
    "${DATALINK_SOURCE_ROOT:-./storage/datasources}" \
    "$(dirname "${DATALINK_DATABASE_PATH:-./storage/datalink/datalink.db}")"

exec python -m uvicorn server.main:app \
    --app-dir services/datalink \
    --host 0.0.0.0 \
    --port 8281
