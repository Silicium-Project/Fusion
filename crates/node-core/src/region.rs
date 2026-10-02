//! Rectangle of an image addressed by a task (a fragment of a job).

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
