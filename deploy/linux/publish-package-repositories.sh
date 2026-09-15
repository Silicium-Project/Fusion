#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-prod}"
CHANNEL_TOOL="$ROOT/deploy/release/channel.py"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/publish-package-repositories.sh $ROOT" >&2
  exit 1
fi
[[ -f "$CHANNEL_TOOL" ]] || { echo "Missing channel contract: $CHANNEL_TOOL" >&2; exit 1; }
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null
channel_field() { python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field "$1"; }

CONFIG_DIR="${SILICIUM_CONFIG_DIR:-$(channel_field config_dir)}"
DATA_ROOT="${SILICIUM_DATA_ROOT:-$(channel_field data_dir)}"
PUBLIC_BASE_URL="${SILICIUM_DOWNLOAD_BASE_URL:-$(channel_field public_base_url)/downloads}"
DOWNLOADS_DIR="${SILICIUM_DOWNLOADS_DIR:-$DATA_ROOT/downloads}"
PACKAGE_SUITE="${SILICIUM_PACKAGE_REPOSITORY_SUITE:-stable}"
if [[ "$RELEASE_CHANNEL" == "dev" && -z "${SILICIUM_PACKAGE_REPOSITORY_SUITE:-}" ]]; then
  PACKAGE_SUITE=dev
fi

case "$RELEASE_CHANNEL" in
  dev) package_suffix="-dev" ;;
  prod) package_suffix="" ;;
  *) echo "Unsupported release channel: $RELEASE_CHANNEL" >&2; exit 1 ;;
esac

deb_source="$DOWNLOADS_DIR/silicium-node-linux${package_suffix}.deb"
rpm_source="$DOWNLOADS_DIR/silicium-node-linux${package_suffix}.rpm"
if [[ ! -s "$deb_source" || ! -s "$rpm_source" ]]; then
  message="package repository deferred: both $deb_source and $rpm_source are required"
  if [[ "${SILICIUM_PACKAGE_REPOSITORY_REQUIRED:-0}" == "1" ]]; then
    echo "$message" >&2
    exit 1
  fi
  echo "$message"
  exit 0
fi

for tool in dpkg-deb dpkg-scanpackages apt-ftparchive gpg; do
  command -v "$tool" >/dev/null || { echo "$tool is required to publish the APT repository." >&2; exit 1; }
done

apt_root="$DOWNLOADS_DIR/apt"
apt_pool="$apt_root/pool/main"
apt_distribution="$apt_root/dists/$PACKAGE_SUITE"
apt_binary="$apt_distribution/main/binary-amd64"
rpm_root="$DOWNLOADS_DIR/rpm"
install -d -m 0755 "$apt_pool" "$apt_binary" "$rpm_root"
rm -rf -- "$apt_root/dists/$PACKAGE_SUITE" "$apt_pool"/silicium-node_*.deb "$rpm_root/repodata"
install -d -m 0755 "$apt_pool" "$apt_binary"

package_name="$(dpkg-deb -f "$deb_source" Package)"
package_version="$(dpkg-deb -f "$deb_source" Version)"
package_arch="$(dpkg-deb -f "$deb_source" Architecture)"
[[ "$package_arch" == "amd64" ]] || { echo "Unsupported package architecture: $package_arch" >&2; exit 1; }
[[ "$package_name" =~ ^[A-Za-z0-9.+-]+$ ]] || { echo "Invalid package name: $package_name" >&2; exit 1; }
apt_package="$apt_pool/${package_name}_${package_version}_${package_arch}.deb"
ln -f -- "$deb_source" "$apt_package" 2>/dev/null || cp -f -- "$deb_source" "$apt_package"

pushd "$apt_root" >/dev/null
dpkg-scanpackages --arch "$package_arch" pool/main /dev/null > "$apt_binary/Packages"
popd >/dev/null
gzip -9c "$apt_binary/Packages" > "$apt_binary/Packages.gz"

apt_config="$(mktemp)"
key_home="$CONFIG_DIR/package-signing-gnupg"
cleanup() { rm -f -- "$apt_config"; }
trap cleanup EXIT
install -d -m 0700 "$key_home"
cat > "$apt_config" <<EOF
APT::FTPArchive::Release::Origin "Silicium Project";
APT::FTPArchive::Release::Label "Silicium Node";
APT::FTPArchive::Release::Suite "$PACKAGE_SUITE";
APT::FTPArchive::Release::Codename "$PACKAGE_SUITE";
APT::FTPArchive::Release::Components "main";
APT::FTPArchive::Release::Architectures "amd64";
EOF
apt-ftparchive -c "$apt_config" release "$apt_distribution" > "$apt_distribution/Release"

key_uid="Silicium Packages ($RELEASE_CHANNEL) <packages-${RELEASE_CHANNEL}@silicium.invalid>"
key_id="$(gpg --batch --homedir "$key_home" --with-colons --list-secret-keys "$key_uid" 2>/dev/null | awk -F: '$1 == "sec" {print $5; exit}' || true)"
if [[ -z "$key_id" ]]; then
  gpg --batch --pinentry-mode loopback --passphrase "" --homedir "$key_home" \
    --quick-generate-key "$key_uid" ed25519 sign 0
  key_id="$(gpg --batch --homedir "$key_home" --with-colons --list-secret-keys "$key_uid" 2>/dev/null | awk -F: '$1 == "sec" {print $5; exit}' || true)"
fi
[[ -n "$key_id" ]] || { echo "Could not resolve the APT signing key." >&2; exit 1; }
gpg --batch --yes --homedir "$key_home" --local-user "$key_id" \
  --clearsign --output "$apt_distribution/InRelease" "$apt_distribution/Release"
gpg --batch --yes --homedir "$key_home" --local-user "$key_id" \
  --armor --detach-sign --output "$apt_distribution/Release.gpg" "$apt_distribution/Release"
gpg --batch --homedir "$key_home" --armor --export "$key_id" > "$apt_root/silicium-packages.asc"
chmod 0644 "$apt_root/silicium-packages.asc" "$apt_distribution/InRelease" "$apt_distribution/Release.gpg"

cat > "$apt_root/silicium.sources" <<EOF
Types: deb
URIs: ${PUBLIC_BASE_URL%/}/apt
Suites: $PACKAGE_SUITE
Components: main
Architectures: amd64
Signed-By: /etc/apt/keyrings/silicium-${RELEASE_CHANNEL}.gpg
EOF
chmod 0644 "$apt_root/silicium.sources"

if ! command -v createrepo_c >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends createrepo-c
  else
    echo "createrepo_c is required to publish the DNF repository." >&2
    exit 1
  fi
fi
rpm_package="$rpm_root/silicium-node${package_suffix}.rpm"
ln -f -- "$rpm_source" "$rpm_package" 2>/dev/null || cp -f -- "$rpm_source" "$rpm_package"
createrepo_c "$rpm_root"
cat > "$rpm_root/silicium-node.repo" <<EOF
[silicium-${RELEASE_CHANNEL}]
name=Silicium Node (${RELEASE_CHANNEL})
baseurl=${PUBLIC_BASE_URL%/}/rpm
enabled=1
gpgcheck=0
repo_gpgcheck=0
metadata_expire=300
EOF
chmod 0644 "$rpm_root/silicium-node.repo"

echo "Package repositories published for $RELEASE_CHANNEL ($PACKAGE_SUITE)."
echo "  APT: ${PUBLIC_BASE_URL%/}/apt"
echo "  DNF: ${PUBLIC_BASE_URL%/}/rpm"
