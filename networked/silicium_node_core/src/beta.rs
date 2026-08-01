use rand::Rng;
use rand_distr::{Beta, Distribution};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct BetaPosterior {
    version: u8,
    alpha: f64,
    beta: f64,
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum BetaCodecError {
    #[error("beta distribution parameters must be finite and strictly positive")]
    InvalidParameters,
    #[error("beta codec version mismatch: expected {expected}, got {actual}")]
    VersionMismatch { expected: u8, actual: u8 },
    #[error("bincode encode failed: {0}")]
    Encode(String),
    #[error("bincode decode failed: {0}")]
    Decode(String),
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
struct BetaEnvelope {
    version: u8,
    alpha: f64,
    beta: f64,
}

impl Default for BetaPosterior {
    fn default() -> Self {
        Self::new(2.0, 2.0).expect("valid default posterior")
    }
}

impl BetaPosterior {
    pub const VERSION: u8 = 1;

    pub fn new(alpha: f64, beta: f64) -> Result<Self, BetaCodecError> {
        if !alpha.is_finite() || !beta.is_finite() || alpha <= 0.0 || beta <= 0.0 {
            return Err(BetaCodecError::InvalidParameters);
        }
        Ok(Self {
            version: Self::VERSION,
            alpha,
            beta,
        })
    }

    pub fn alpha(self) -> f64 {
        self.alpha
    }

    pub fn beta(self) -> f64 {
        self.beta
    }

    pub fn mean(self) -> f64 {
        self.alpha / (self.alpha + self.beta)
    }

    pub fn observe(&mut self, success: bool, weight: f64) {
        let weight = weight.max(0.0);
        if success {
            self.alpha += weight;
        } else {
            self.beta += weight;
        }
    }

    pub fn with_scale_hint(scale: f64) -> Self {
        let scale = scale.clamp(0.0, 1.0);
        let alpha = 2.0 + (2.0 * scale);
        let beta = 2.0 + (2.0 * (1.0 - scale));
        Self::new(alpha, beta).expect("scale hint yields valid parameters")
    }

    pub fn sample<R: Rng + ?Sized>(self, rng: &mut R) -> f64 {
        Beta::new(self.alpha, self.beta)
            .expect("posterior parameters are validated")
            .sample(rng)
    }

    pub fn to_bytes(self) -> Result<Vec<u8>, BetaCodecError> {
        let envelope = BetaEnvelope {
            version: self.version,
            alpha: self.alpha,
            beta: self.beta,
        };
        bincode::serde::encode_to_vec(envelope, bincode::config::standard())
            .map_err(|e| BetaCodecError::Encode(e.to_string()))
    }

    pub fn from_bytes(bytes: &[u8]) -> Result<Self, BetaCodecError> {
        let (envelope, _): (BetaEnvelope, usize) =
            bincode::serde::decode_from_slice(bytes, bincode::config::standard())
                .map_err(|e| BetaCodecError::Decode(e.to_string()))?;
        if envelope.version != Self::VERSION {
            return Err(BetaCodecError::VersionMismatch {
                expected: Self::VERSION,
                actual: envelope.version,
            });
        }
        Self::new(envelope.alpha, envelope.beta)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;

    #[test]
    fn observes_success_and_failure() {
        let mut posterior = BetaPosterior::new(2.0, 2.0).unwrap();
        posterior.observe(true, 1.0);
        posterior.observe(false, 2.0);
        assert_eq!(posterior.alpha(), 3.0);
        assert_eq!(posterior.beta(), 4.0);
    }

    #[test]
    fn roundtrip_serialization() {
        let posterior = BetaPosterior::new(3.5, 7.25).unwrap();
        let bytes = posterior.to_bytes().unwrap();
        assert_eq!(BetaPosterior::from_bytes(&bytes).unwrap(), posterior);
    }

    #[test]
    fn deterministic_sampling_with_seed() {
        let posterior = BetaPosterior::new(2.0, 3.0).unwrap();
        let mut rng = rand::rngs::StdRng::seed_from_u64(42);
        let first = posterior.sample(&mut rng);
        let mut rng2 = rand::rngs::StdRng::seed_from_u64(42);
        let second = posterior.sample(&mut rng2);
        assert_eq!(first, second);
    }
}
