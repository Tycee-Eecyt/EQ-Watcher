#!/bin/sh
cd "$(dirname "$0")" || exit 1
port="${LINUX_GINA_PORT:-8765}"
log_dir="${LINUX_GINA_LOG_DIR:-/dev/shm/linux-gina-logs}"
mkdir -p "$log_dir"
if command -v xfconf-query >/dev/null 2>&1; then
  xfconf-query -c xfwm4 -p /general/use_compositing -n -t bool -s true >/dev/null 2>&1 || true
fi
if command -v curl >/dev/null 2>&1 &&
  curl -fsS "http://127.0.0.1:${port}/api/ping" 2>/dev/null | grep -q '"app": "eq-watcher"'; then
  curl -fsS "http://127.0.0.1:${port}/api/open-ui" >/dev/null 2>&1
  exit 0
fi
setsid -f sh -c '
  env -u __NV_PRIME_RENDER_OFFLOAD -u __GLX_VENDOR_LIBRARY_NAME -u __VK_LAYER_NV_optimus GDK_BACKEND=x11 python3 linux_gina.py
  status=$?
  printf "%s EQ Watcher exited with status %s\n" "$(date "+%Y-%m-%d %H:%M:%S %Z")" "$status"
' >>"$log_dir/linux-gina.log" 2>&1 &
exit 0
