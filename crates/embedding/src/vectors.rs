//! The vectors a worker publishes for its passages: a [`VectorBlock`].
//!
//! Binary layout, little-endian:
//!
//! | Offset | Size | Field |
//! | --- | --- | --- |
//! | 0 | 8 | magic `SLCMVEC1` |
//! | 8 | 4 | dimension `d` (u32) |
//! | 12 | 4 | vector count `n` (u32) |
//! | 16 | 8 | id of the first passage (u64) |
//! | 24 | 8 | reserved, zero |
//! | 32 | `4·n·d` | `n` vectors of `d` f32 |
//!
//! The header ties the vectors to their passages: the publisher and the
//! verifiers refuse a block whose dimension, first id or count is not the
//! fragment's ([`VectorBlock::check_shape`]), or whose vectors are not unit
//! vectors ([`VectorBlock::check_unit`]).

use crate::{Error, Result};

/// First bytes of a vector block.
pub const MAGIC: &[u8; 8] = b"SLCMVEC1";
/// Size of the header.
pub const HEADER_BYTES: usize = 32;
/// Largest distance of a vector's length from 1.
pub const UNIT_TOLERANCE: f32 = 1e-3;

/// Vectors of consecutive passages.
#[derive(Debug, Clone, PartialEq)]
pub struct VectorBlock {
    pub dimension: usize,
    pub first_id: u64,
    /// `count × dimension` values, vector after vector.
    pub values: Vec<f32>,
}

impl VectorBlock {
    /// Block of `vectors`, the first one being passage `first_id`.
    pub fn new(dimension: usize, first_id: u64, vectors: &[Vec<f32>]) -> Result<Self> {
        if vectors.iter().any(|vector| vector.len() != dimension) {
            return Err(Error::Format("vector of the wrong dimension".into()));
        }
        Ok(Self {
            dimension,
            first_id,
            values: vectors.concat(),
        })
    }

    /// Number of vectors.
    pub fn count(&self) -> usize {
        self.values.len().checked_div(self.dimension).unwrap_or(0)
    }

    /// Vector `index` of the block.
    pub fn vector(&self, index: usize) -> Option<&[f32]> {
        let start = index.checked_mul(self.dimension)?;
        self.values.get(start..start + self.dimension)
    }

    /// The binary form (see the module documentation).
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::with_capacity(HEADER_BYTES + self.values.len() * 4);
        bytes.extend_from_slice(MAGIC);
        bytes.extend_from_slice(&(self.dimension as u32).to_le_bytes());
        bytes.extend_from_slice(&(self.count() as u32).to_le_bytes());
        bytes.extend_from_slice(&self.first_id.to_le_bytes());
        bytes.extend_from_slice(&[0u8; 8]);
        for value in &self.values {
            bytes.extend_from_slice(&value.to_le_bytes());
        }
        bytes
    }

    /// Parses the binary form, refusing any inconsistency.
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        if bytes.len() < HEADER_BYTES || &bytes[..8] != MAGIC {
            return Err(Error::Format("not a vector block".into()));
        }
        let dimension = u32::from_le_bytes(bytes[8..12].try_into().expect("4 bytes")) as usize;
        let count = u32::from_le_bytes(bytes[12..16].try_into().expect("4 bytes")) as usize;
        let first_id = u64::from_le_bytes(bytes[16..24].try_into().expect("8 bytes"));
        let expected = count
            .checked_mul(dimension)
            .and_then(|values| values.checked_mul(4))
            .and_then(|body| body.checked_add(HEADER_BYTES));
        if dimension == 0 || expected != Some(bytes.len()) {
            return Err(Error::Format(
                "vector block size does not match its header".into(),
            ));
        }
        let values = bytes[HEADER_BYTES..]
            .as_chunks::<4>()
            .0
            .iter()
            .map(|value| f32::from_le_bytes(*value))
            .collect();
        Ok(Self {
            dimension,
            first_id,
            values,
        })
    }

    /// Checks that the block holds the vectors of passages
    /// `first_id..first_id + count`, of size `dimension`.
    pub fn check_shape(&self, dimension: usize, first_id: u64, count: u64) -> Result<()> {
        if self.dimension != dimension || self.first_id != first_id || self.count() as u64 != count
        {
            return Err(Error::Format(format!(
                "block of {} vectors of {} from passage {}, expected {count} of {dimension} from {first_id}",
                self.count(),
                self.dimension,
                self.first_id
            )));
        }
        Ok(())
    }

    /// Checks that every value is finite and every vector has length 1.
    pub fn check_unit(&self) -> Result<()> {
        for index in 0..self.count() {
            let vector = self.vector(index).expect("index below count");
            let norm = dot(vector, vector).sqrt();
            if !norm.is_finite() || (norm - 1.0).abs() > UNIT_TOLERANCE {
                return Err(Error::Format(format!(
                    "vector {index} is not a unit vector"
                )));
            }
        }
        Ok(())
    }
}

/// Dot product (the cosine similarity of two unit vectors).
pub fn dot(left: &[f32], right: &[f32]) -> f32 {
    left.iter().zip(right).map(|(a, b)| a * b).sum()
}

/// Cosine similarity of two vectors of any length.
pub fn cosine(left: &[f32], right: &[f32]) -> f32 {
    let norms = dot(left, left).sqrt() * dot(right, right).sqrt();
    if norms == 0.0 || !norms.is_finite() {
        return 0.0;
    }
    dot(left, right) / norms
}

#[cfg(test)]
mod tests {
    use super::*;

    fn unit(values: &[f32]) -> Vec<f32> {
        let norm = dot(values, values).sqrt();
        values.iter().map(|v| v / norm).collect()
    }

    #[test]
    fn a_block_round_trips_through_bytes() {
        let block =
            VectorBlock::new(3, 40, &[unit(&[1.0, 2.0, 3.0]), unit(&[0.0, 1.0, 0.0])]).unwrap();
        let bytes = block.to_bytes();
        assert_eq!(bytes.len(), HEADER_BYTES + 2 * 3 * 4);
        let parsed = VectorBlock::parse(&bytes).unwrap();
        assert_eq!(parsed, block);
        parsed.check_shape(3, 40, 2).unwrap();
        parsed.check_unit().unwrap();
    }

    #[test]
    fn inconsistent_blocks_are_refused() {
        let block = VectorBlock::new(2, 0, &[unit(&[1.0, 1.0])]).unwrap();
        let mut bytes = block.to_bytes();
        bytes.push(0);
        assert!(VectorBlock::parse(&bytes).is_err(), "trailing byte");
        assert!(VectorBlock::parse(b"SLCMVEC0________________________").is_err());
        assert!(block.check_shape(2, 1, 1).is_err(), "wrong first passage");
        assert!(block.check_shape(2, 0, 2).is_err(), "wrong count");
        assert!(block.check_shape(3, 0, 1).is_err(), "wrong dimension");
        assert!(VectorBlock::new(2, 0, &[vec![1.0]]).is_err());
    }

    #[test]
    fn non_unit_or_non_finite_vectors_are_refused() {
        assert!(
            VectorBlock::new(2, 0, &[vec![1.0, 1.0]])
                .unwrap()
                .check_unit()
                .is_err()
        );
        assert!(
            VectorBlock::new(2, 0, &[vec![f32::NAN, 0.0]])
                .unwrap()
                .check_unit()
                .is_err()
        );
        assert!(
            VectorBlock::new(2, 0, &[vec![0.0, 0.0]])
                .unwrap()
                .check_unit()
                .is_err()
        );
    }

    #[test]
    fn cosine_ignores_length() {
        assert!((cosine(&[1.0, 0.0], &[3.0, 0.0]) - 1.0).abs() < 1e-6);
        assert_eq!(cosine(&[1.0, 0.0], &[0.0, 0.0]), 0.0);
        assert!(cosine(&[1.0, 0.0], &[0.0, 1.0]).abs() < 1e-6);
    }
}
