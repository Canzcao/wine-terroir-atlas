#!/usr/bin/env bash
# 风土图鉴 · 一键构建并发布到腾讯云
#   ./deploy/deploy.sh
# 只做三件事：本地构建 -> rsync 到服务器 -> 重启独立进程
# 不会碰 VINCODE 主站的任何文件和进程。

set -euo pipefail

SRC="${SRC:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LOCAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ★ 部署目标必须由环境变量提供（开源版不含任何具体服务器地址）
#   例：SERVER=root@your.server.ip bash deploy/deploy.sh
SERVER="${SERVER:?请设置 SERVER，例如 SERVER=root@1.2.3.4}"
REMOTE_DIR="${REMOTE_DIR:-/opt/terroir-atlas}"
APP_NAME="${APP_NAME:-terroir-atlas}"
NODE_BIN="${NODE_BIN:-node}"
NPM_BIN="${NPM_BIN:-npm}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new)

echo "==> 1/4 构建站点（含最新 data/catalog-seed.json、events.json）"
cd "$SRC"
"$NPM_BIN" run build
cp dist/server/index.js "$LOCAL/dist/server/index.js"
echo "    Worker 产物: $(du -h "$LOCAL/dist/server/index.js" | cut -f1)"

echo "==> 2/4 本地自检"
cd "$LOCAL"
"$NODE_BIN" --no-warnings smoke_test.mjs

echo "==> 3/4 同步到 $SERVER:$REMOTE_DIR"
ssh "${SSH_OPTS[@]}" "$SERVER" "mkdir -p '$REMOTE_DIR/var'"
# 注意：macOS 自带的是 openrsync，不认识 --chown，因此改为 --no-owner --no-group，
# 属主在服务器端用 chown -R root:root 统一修正（见第 4 步）。
rsync -az --delete -e "ssh ${SSH_OPTS[*]}" \
  --no-owner --no-group \
  --exclude 'var/' \
  --exclude 'node_modules/' \
  --exclude '*.log' \
  "$LOCAL/" "$SERVER:$REMOTE_DIR/"

echo "==> 4/4 修正属主、重启进程并探活"
ssh "${SSH_OPTS[@]}" "$SERVER" "chown -R root:root '$REMOTE_DIR' && cd '$REMOTE_DIR' && \
  (pm2 restart '$APP_NAME' --update-env 2>/dev/null || pm2 start ecosystem.config.cjs) && \
  pm2 save >/dev/null 2>&1 || true; \
  sleep 2; curl -s --max-time 8 -o /dev/null -w '本机 /healthz -> %{http_code}\n' http://127.0.0.1:3020/healthz"

echo "==> 完成。线上地址： ${PUBLIC_URL:-（见你的服务器配置）}"
