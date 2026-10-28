#!/bin/sh
set -eu

app_dir="${XDG_DATA_HOME:-$HOME/.local/share}/eq-watcher"
bin_dir="$HOME/.local/bin"
desktop_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

command -v python3 >/dev/null 2>&1 || {
  echo "Python 3 is required. Install it with your distribution's package manager." >&2
  exit 1
}

mkdir -p "$app_dir/data" "$bin_dir" "$desktop_dir"
cp "$source_dir/linux_gina.py" "$app_dir/linux_gina.py"
cp "$source_dir/run-linux-gina.sh" "$app_dir/run-linux-gina.sh"
chmod +x "$app_dir/linux_gina.py" "$app_dir/run-linux-gina.sh"

for source in assets midi; do
  if [ -d "$source_dir/data/$source" ]; then
    rm -rf "$app_dir/data/$source"
    cp -R "$source_dir/data/$source" "$app_dir/data/$source"
  fi
done
if [ -f "$source_dir/data/p99_spell_catalog.json" ]; then
  cp "$source_dir/data/p99_spell_catalog.json" "$app_dir/data/p99_spell_catalog.json"
fi

ln -sf "$app_dir/run-linux-gina.sh" "$bin_dir/eq-watcher"
sed "s|@APP_DIR@|$app_dir|g" "$source_dir/packaging/eq-watcher.desktop.in" > "$desktop_dir/eq-watcher.desktop"
chmod 644 "$desktop_dir/eq-watcher.desktop"

echo "EQ Watcher installed to $app_dir"
echo "Launch it from your applications menu or run: $bin_dir/eq-watcher"
echo "For native overlays on Debian/Ubuntu, install: python3-gi python3-cairo gir1.2-gtk-3.0"
