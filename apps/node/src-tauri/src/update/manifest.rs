//! Update manifest: fetch, release selection for this platform, validation,
//! Ed25519 signature check and version comparison.

use crate::*;

pub(crate) fn fetch_update_release() -> Result<UpdateRelease, String> {
    curl_get(update_manifest_url(), 15)
        .and_then(|output| {
            serde_json::from_str::<Value>(output.trim())
                .map_err(|error| format!("update_manifest_invalid:{error}"))
        })
        .and_then(|manifest| select_update_release(&manifest))
        .map_err(|error| format!("update_manifest_unavailable:{error}"))
}

pub(crate) fn select_update_release(manifest: &Value) -> Result<UpdateRelease, String> {
    let mut candidates = Vec::new();
    if let Some(channel) = manifest
        .get("channels")
        .and_then(Value::as_object)
        .and_then(|channels| channels.get(release_channel()))
    {
        candidates.push(channel.clone());
    }
    if let Some(releases) = manifest.get("releases").and_then(Value::as_array) {
        candidates.extend(releases.iter().cloned());
    }
    let mut valid = Vec::new();
    for candidate in candidates {
        let Ok(mut release) = serde_json::from_value::<UpdateRelease>(candidate) else {
            continue;
        };
        if release.channel.trim().is_empty() {
            release.channel = release_channel().to_string();
        }
        if release.channel != release_channel()
            || !update_platform_matches(&release.platform)
            || validate_update_release(&release).is_err()
        {
            continue;
        }
        valid.push(release);
    }
    valid
        .into_iter()
        .max_by(|left, right| compare_versions(&left.version, &right.version))
        .ok_or_else(|| format!("update_channel_missing_or_untrusted:{}", release_channel()))
}

pub(crate) fn update_platform() -> String {
    format!("{}-{}", env::consts::OS, env::consts::ARCH)
}

pub(crate) fn update_platform_matches(platform: &str) -> bool {
    let candidate = platform.trim().to_ascii_lowercase();
    if candidate.is_empty() {
        // Schema v1 only contained Windows NSIS releases. Keeping this legacy
        // fallback Windows-only prevents a Linux client from installing .exe.
        return cfg!(target_os = "windows");
    }
    candidate == update_platform()
}

pub(crate) fn validate_update_release(release: &UpdateRelease) -> Result<(), String> {
    if release.version.trim().is_empty() {
        return Err("update_version_missing".to_string());
    }
    if !trusted_update_download_url(&release.url, &release.channel) {
        return Err("update_url_untrusted".to_string());
    }
    let hash = release.sha256.trim();
    if hash.len() != 64 || !hash.chars().all(|character| character.is_ascii_hexdigit()) {
        return Err("update_sha256_invalid".to_string());
    }
    if !release.content_id.trim().eq_ignore_ascii_case(hash) {
        return Err("update_content_id_mismatch".to_string());
    }
    if release.signing_key_id.trim() != UPDATE_SIGNING_KEY_ID {
        return Err("update_signing_key_untrusted".to_string());
    }
    verify_update_signature(release)?;
    Ok(())
}

/// The development VPN is an explicit origin; the signature and channel are
/// still checked independently. Keep the old public dev URL compatible.
pub(crate) fn trusted_update_download_url(url: &str, channel: &str) -> bool {
    let lower = url.to_ascii_lowercase();
    if lower.contains("/../") || lower.contains("%2e") || lower.contains('#') || lower.contains('?')
    {
        return false;
    }
    url.starts_with("https://vps-910c1dbc.vps.ovh.net/downloads/")
        || (channel == "dev" && url.starts_with("https://10.77.0.1:8443/downloads/"))
}

pub(crate) fn update_signature_payload(release: &UpdateRelease) -> Vec<u8> {
    format!(
        "silicium-update-v1\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n",
        release.channel,
        release.platform,
        release.version,
        release.sha256.to_ascii_lowercase(),
        release.size_bytes,
        release.url,
        release.content_id.to_ascii_lowercase(),
    )
    .into_bytes()
}

pub(crate) fn legacy_update_signature_payload(release: &UpdateRelease) -> Vec<u8> {
    format!(
        "silicium-update-v1\n{}\n{}\n{}\n{}\n{}\n{}\n",
        release.channel,
        release.version,
        release.sha256.to_ascii_lowercase(),
        release.size_bytes,
        release.url,
        release.content_id.to_ascii_lowercase(),
    )
    .into_bytes()
}

pub(crate) fn verify_update_signature(release: &UpdateRelease) -> Result<(), String> {
    let public_key = BASE64_STANDARD
        .decode(UPDATE_SIGNING_PUBLIC_KEY_B64)
        .map_err(|_| "update_public_key_invalid".to_string())?;
    let public_key: [u8; 32] = public_key
        .try_into()
        .map_err(|_| "update_public_key_invalid".to_string())?;
    let verifying_key = VerifyingKey::from_bytes(&public_key)
        .map_err(|_| "update_public_key_invalid".to_string())?;
    let signature = BASE64_STANDARD
        .decode(release.signature.trim())
        .map_err(|_| "update_signature_invalid".to_string())?;
    let signature =
        Signature::from_slice(&signature).map_err(|_| "update_signature_invalid".to_string())?;
    if verifying_key
        .verify(&update_signature_payload(release), &signature)
        .is_ok()
    {
        return Ok(());
    }
    // Releases published before platform-specific artifacts were added did
    // not include `platform` in the signed payload. Accept that legacy form
    // only when the field is absent; a non-empty platform must be signed.
    if release.platform.trim().is_empty()
        && verifying_key
            .verify(&legacy_update_signature_payload(release), &signature)
            .is_ok()
    {
        return Ok(());
    }
    Err("update_signature_untrusted".to_string())
}

#[cfg(test)]
pub(crate) fn version_is_newer(candidate: &str, current: &str) -> bool {
    compare_versions(candidate, current) == Ordering::Greater
}

pub(crate) fn release_requires_update(
    candidate_version: &str,
    candidate_build: &str,
    current_version: &str,
    current_build: &str,
) -> bool {
    match compare_versions(candidate_version, current_version) {
        Ordering::Greater => true,
        Ordering::Less => false,
        Ordering::Equal => {
            let candidate_build = candidate_build.trim();
            !candidate_build.is_empty() && candidate_build != current_build.trim()
        }
    }
}

pub(crate) fn compare_versions(left: &str, right: &str) -> Ordering {
    let parse = |value: &str| {
        let clean = value.trim().trim_start_matches('v');
        let mut sections = clean.splitn(2, '-');
        let core = sections
            .next()
            .unwrap_or("")
            .split('.')
            .map(|part| part.parse::<u64>().unwrap_or(0))
            .collect::<Vec<_>>();
        let pre = sections.next().unwrap_or("").to_string();
        (core, pre)
    };
    let (left_core, left_pre) = parse(left);
    let (right_core, right_pre) = parse(right);
    for index in 0..left_core.len().max(right_core.len()).max(3) {
        let ordering = left_core
            .get(index)
            .copied()
            .unwrap_or(0)
            .cmp(&right_core.get(index).copied().unwrap_or(0));
        if ordering != Ordering::Equal {
            return ordering;
        }
    }
    match (left_pre.is_empty(), right_pre.is_empty()) {
        (true, false) => Ordering::Greater,
        (false, true) => Ordering::Less,
        (true, true) => Ordering::Equal,
        (false, false) => {
            let left_parts = left_pre.split('.').collect::<Vec<_>>();
            let right_parts = right_pre.split('.').collect::<Vec<_>>();
            for index in 0..left_parts.len().max(right_parts.len()) {
                let left_part = left_parts.get(index).copied().unwrap_or("");
                let right_part = right_parts.get(index).copied().unwrap_or("");
                let ordering = match (left_part.parse::<u64>(), right_part.parse::<u64>()) {
                    (Ok(left_number), Ok(right_number)) => left_number.cmp(&right_number),
                    (Ok(_), Err(_)) => Ordering::Less,
                    (Err(_), Ok(_)) => Ordering::Greater,
                    (Err(_), Err(_)) => left_part.cmp(right_part),
                };
                if ordering != Ordering::Equal {
                    return ordering;
                }
            }
            Ordering::Equal
        }
    }
}
