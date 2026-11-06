#!/bin/sh
# 主后端启动：统一存储路径 -> 数据库迁移 -> 单 worker uvicorn。
set -eu

if [ -n "${CHATBI_STORAGE_ROOT:-}" ]; then
    export DATASOURCE_ROOT="$CHATBI_STORAGE_ROOT/datasources"
    export ARTIFACT_ROOT="$CHATBI_STORAGE_ROOT/artifacts"
    export SCRIPT_WORKSPACE_ROOT="$CHATBI_STORAGE_ROOT/script-workspaces"
    export RUNTIME_TRACE_ROOT="$CHATBI_STORAGE_ROOT/runtime-traces"
    export SESSION_WORKSPACE_ROOT="$CHATBI_STORAGE_ROOT/session-workspaces"
    export METADATA_DATABASE_URL="sqlite+aiosqlite:///$CHATBI_STORAGE_ROOT/metadata.db"
fi

mkdir -p \
    "${DATASOURCE_ROOT:-./storage/datasources}" \
    "${ARTIFACT_ROOT:-./storage/artifacts}" \
    "${SCRIPT_WORKSPACE_ROOT:-./storage/script-workspaces}" \
    "${RUNTIME_TRACE_ROOT:-./storage/runtime-traces}" \
    "${SESSION_WORKSPACE_ROOT:-./storage/session-workspaces}"

python -m alembic upgrade head

exec python -m uvicorn server.asgi:app \
    --app-dir apps/api \
    --host 0.0.0.0 \
    --port 8280
