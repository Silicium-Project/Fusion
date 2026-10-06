//! Part of the input addressed by a task (a fragment of a job): a rectangle
//! of an image ([`Region`]) or a range of bytes ([`ByteRange`]).

use serde::{Deserialize, Serialize};

/// Rectangle of an image, in pixels (`*_end` exclusive).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Region {
    pub x_start: u32,
    pub x_end: u32,
    pub y_start: u32,
    pub y_end: u32,
}

impl Region {
    /// Largest image side a region may address.
    pub const MAX_SIDE: u32 = 16_384;

    /// True when the rectangle is non-empty and inside the largest image.
    pub fn is_valid(&self) -> bool {
        self.x_start < self.x_end
            && self.y_start < self.y_end
            && self.x_end <= Self::MAX_SIDE
            && self.y_end <= Self::MAX_SIDE
    }
}

/// Range of bytes of a task's input (`end` exclusive), for workloads that
/// split a file into chunks.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ByteRange {
    pub start: u64,
    pub end: u64,
}

impl ByteRange {
    /// Largest input a range may address (1 GiB).
    pub const MAX_END: u64 = 1 << 30;

    /// Number of bytes in the range.
    pub fn len(&self) -> u64 {
        self.end.saturating_sub(self.start)
    }

    /// True when the range addresses no byte.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// True when the range is ordered and inside the largest input. An empty
    /// range is valid: it is the only chunk of an empty input.
    pub fn is_valid(&self) -> bool {
        self.start <= self.end && self.end <= Self::MAX_END
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn byte_ranges_are_checked() {
        assert!(ByteRange { start: 0, end: 0 }.is_valid());
        assert!(ByteRange { start: 3, end: 10 }.is_valid());
        assert_eq!(ByteRange { start: 3, end: 10 }.len(), 7);
        assert!(!ByteRange { start: 10, end: 3 }.is_valid());
        assert!(
            !ByteRange {
                start: 0,
                end: ByteRange::MAX_END + 1
            }
            .is_valid()
        );
    }
}
