//! ZIP archives of documents (a folder sent at once, or several files the
//! site bundled). Entries are read one level deep only: an archive inside
//! the archive is skipped, so that a small upload cannot expand without
//! bound. Folders, hidden files and Office lock files (`~$...`) are ignored.

use super::{Extraction, Limits, SkipReason, read_single};
use std::io::{Cursor, Read};

/// Reads every document of the archive `bytes` into `out`.
pub(super) fn read(bytes: &[u8], limits: &Limits, out: &mut Extraction) {
    let Ok(mut archive) = zip::ZipArchive::new(Cursor::new(bytes)) else {
        out.skip("archive.zip", SkipReason::Unreadable);
        return;
    };
    let mut total: u64 = 0;
    let mut files = 0usize;
    for index in 0..archive.len() {
        let Ok(mut entry) = archive.by_index(index) else {
            continue;
        };
        let name = entry.name().replace('\\', "/");
        if entry.is_dir() || is_ignored(&name) {
            continue;
        }
        files += 1;
        if files > limits.max_files {
            out.skip(&name, SkipReason::TooLarge);
            continue;
        }
        let declared = entry.size();
        if declared > limits.max_file_bytes
            || total.saturating_add(declared) > limits.max_total_bytes
        {
            out.skip(&name, SkipReason::TooLarge);
            continue;
        }
        // The declared size may lie: read at most one byte over the limit.
        let mut content = Vec::new();
        let budget = limits.max_file_bytes.min(limits.max_total_bytes - total);
        if (&mut entry)
            .take(budget + 1)
            .read_to_end(&mut content)
            .is_err()
        {
            out.skip(&name, SkipReason::Unreadable);
            continue;
        }
        if content.len() as u64 > budget {
            out.skip(&name, SkipReason::TooLarge);
            continue;
        }
        total += content.len() as u64;
        read_single(&name, &content, out);
    }
}

/// Entries that are not documents of the user.
fn is_ignored(name: &str) -> bool {
    let file = name.rsplit('/').next().unwrap_or(name);
    name.starts_with("__MACOSX/")
        || file.starts_with('.')
        || file.starts_with("~$")
        || file.is_empty()
}
