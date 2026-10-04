#!/usr/bin/env bash
set -euo pipefail

APPIMAGE_PATH="${1:-}"
DEB_PATH="${2:-}"
RPM_PATH="${3:-}"

if [[ -z "$APPIMAGE_PATH" || -z "$DEB_PATH" || -z "$RPM_PATH" ]]; then
  echo "Usage: verify-linux-bundles.sh <AppImage> <deb> <rpm>" >&2
  exit 2
fi
if [[ ! -s "$APPIMAGE_PATH" ]]; then
  echo "AppImage was not produced: $APPIMAGE_PATH" >&2
  exit 1
fi
if [[ ! -s "$DEB_PATH" ]]; then
  echo "Debian package was not produced: $DEB_PATH" >&2
  exit 1
fi
if [[ ! -s "$RPM_PATH" ]]; then
  echo "RPM package was not produced: $RPM_PATH" >&2
  exit 1
fi

# The build script discovers bundles from apps/silicium-node and passes paths
# relative to that directory. The AppImage validation below changes into a
# temporary extraction directory, so retain canonical paths before doing so.
APPIMAGE_PATH="$(realpath "$APPIMAGE_PATH")"
DEB_PATH="$(realpath "$DEB_PATH")"
RPM_PATH="$(realpath "$RPM_PATH")"

# Keep the artifact executable in the release workspace. The deployment step
# also restores this mode after staging it on the VPS; browsers themselves do
# not preserve executable bits when a user downloads an AppImage.
chmod +x "$APPIMAGE_PATH"
if ! file "$APPIMAGE_PATH" | grep -Eiq 'ELF|AppImage|SquashFS'; then
  echo "The AppImage does not look like a valid Linux executable: $APPIMAGE_PATH" >&2
  file "$APPIMAGE_PATH" >&2
  exit 1
fi

if ! dpkg-deb --info "$DEB_PATH" >/dev/null; then
  echo "The Debian package metadata is invalid: $DEB_PATH" >&2
  exit 1
fi

if ! rpm -qip "$RPM_PATH" >/dev/null; then
  echo "The RPM package metadata is invalid: $RPM_PATH" >&2
  exit 1
fi
rpm_runtime_path="$(
  rpm -qpl "$RPM_PATH" \
    | awk '/\/resources\/runtime\/Network\/silicium$/ && !found { print; found = 1 }'
)"
if [[ -z "$rpm_runtime_path" ]]; then
  echo "The RPM package is missing its Network runtime." >&2
  rpm -qpl "$RPM_PATH" | sed -n '1,120p' >&2
  exit 1
fi

extract_root="$(mktemp -d)"
trap 'rm -rf -- "$extract_root"' EXIT
if ! dpkg-deb --extract "$DEB_PATH" "$extract_root/deb" >/dev/null; then
  echo "The Debian package could not be extracted: $DEB_PATH" >&2
  exit 1
fi

deb_runtime_entry="$(
  find "$extract_root/deb/usr/lib" -type f \
    -path '*/resources/runtime/Network/silicium' -print -quit
)"
if [[ -z "$deb_runtime_entry" ]]; then
  echo "The Debian package is missing its Network runtime." >&2
  find "$extract_root/deb/usr" -maxdepth 6 -type f | sort | sed -n '1,80p' >&2
  exit 1
fi

# --appimage-extract works without FUSE and validates the same resource layout
# used when the AppImage is mounted normally.
mkdir -p "$extract_root/appimage"
if ! (
  cd "$extract_root/appimage"
  "$APPIMAGE_PATH" --appimage-extract >/dev/null
); then
  echo "The AppImage could not be self-extracted: $APPIMAGE_PATH" >&2
  exit 1
fi

appimage_runtime_entry="$(
  find "$extract_root/appimage/squashfs-root/usr/lib" -type f \
    -path '*/resources/runtime/Network/silicium' -print -quit
)"
if [[ -z "$appimage_runtime_entry" ]]; then
  echo "The AppImage is missing its Network runtime." >&2
  find "$extract_root/appimage/squashfs-root/usr" -maxdepth 6 -type f | sort | sed -n '1,80p' >&2
  exit 1
fi

echo "Linux bundles verified: AppImage, deb and rpm contain the packaged Network runtime."
printf '  AppImage: %s\n  deb: %s\n  rpm: %s\n' \
  "$appimage_runtime_entry" "$deb_runtime_entry" "$rpm_runtime_path"
