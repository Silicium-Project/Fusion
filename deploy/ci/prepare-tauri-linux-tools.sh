#!/usr/bin/env bash
set -euo pipefail

# Tauri's AppImage bundler downloads these tools lazily. Download them before
# the Rust build so a network failure is fast and never discards a completed
# compilation.
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
tauri_tools_dir="$XDG_CACHE_HOME/tauri"
mkdir -p "$tauri_tools_dir"

curl_args=(
  --fail
  --show-error
  --location
  --connect-timeout 20
  --max-time 120
  --retry 4
  --retry-all-errors
  --retry-delay 3
  --retry-max-time 300
)

download_tool() {
  local destination="$1"
  local url="$2"
  local temporary="${destination}.download.$$"

  if [[ -s "$destination" ]]; then
    chmod +x "$destination"
    echo "Tauri bundler cache hit: $(basename "$destination")"
    return 0
  fi

  echo "Prefetching Tauri bundler tool: $(basename "$destination")"
  if curl "${curl_args[@]}" --output "$temporary" "$url"; then
    chmod +x "$temporary"
    mv -f -- "$temporary" "$destination"
  else
    status=$?
    rm -f -- "$temporary"
    echo "Unable to download Tauri bundler tool: $url" >&2
    return "$status"
  fi
}

download_tool \
  "$tauri_tools_dir/AppRun-x86_64" \
  "https://github.com/tauri-apps/binary-releases/releases/download/apprun-old/AppRun-x86_64"
download_tool \
  "$tauri_tools_dir/linuxdeploy-x86_64.AppImage" \
  "https://github.com/tauri-apps/binary-releases/releases/download/linuxdeploy/linuxdeploy-x86_64.AppImage"
download_tool \
  "$tauri_tools_dir/linuxdeploy-plugin-gtk.sh" \
  "https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gtk/master/linuxdeploy-plugin-gtk.sh"
download_tool \
  "$tauri_tools_dir/linuxdeploy-plugin-gstreamer.sh" \
  "https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gstreamer/master/linuxdeploy-plugin-gstreamer.sh"
download_tool \
  "$tauri_tools_dir/linuxdeploy-plugin-appimage.AppImage" \
  "https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage"

echo "Tauri Linux bundler tools are ready in $tauri_tools_dir"
