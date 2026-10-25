//! Detection and bucketing of the local hardware profile (CPU, memory, GPU hints).

use serde::{Deserialize, Serialize};

pub const VRAM_SHIFT: u32 = 0;
pub const GPU_SHIFT: u32 = 4;
pub const SIMD_SHIFT: u32 = 9;
pub const OS_SHIFT: u32 = 13;

pub const VRAM_MASK: u32 = 0xF << VRAM_SHIFT;
pub const GPU_MASK: u32 = 0x1F << GPU_SHIFT;
pub const SIMD_MASK: u32 = 0xF << SIMD_SHIFT;
pub const OS_MASK: u32 = 0xF << OS_SHIFT;
pub const VALID_MASK: u32 = (VRAM_MASK) | (GPU_MASK) | (SIMD_MASK) | (OS_MASK);
pub const RESERVED_MASK: u32 = !VALID_MASK;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Hash)]
#[repr(u8)]
pub enum VramClass {
    Unknown = 0,
    Vram256 = 1,
    Vram512 = 2,
    Vram1024 = 3,
    Vram2048 = 4,
    Vram4096 = 5,
    Vram8192 = 6,
    Vram16384 = 7,
    Vram32768 = 8,
}

impl VramClass {
    fn code(self) -> u32 {
        self as u32
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Hash, Default)]
pub struct GpuAcceleration {
    pub cuda: bool,
    pub metal: bool,
    pub rocm: bool,
    pub vulkan: bool,
    pub opencl: bool,
}

impl GpuAcceleration {
    fn bits(self) -> u32 {
        let mut bits = 0;
        if self.cuda {
            bits |= 1 << 0;
        }
        if self.metal {
            bits |= 1 << 1;
        }
        if self.rocm {
            bits |= 1 << 2;
        }
        if self.vulkan {
            bits |= 1 << 3;
        }
        if self.opencl {
            bits |= 1 << 4;
        }
        bits
    }

    fn from_bits(bits: u32) -> Self {
        Self {
            cuda: bits & (1 << 0) != 0,
            metal: bits & (1 << 1) != 0,
            rocm: bits & (1 << 2) != 0,
            vulkan: bits & (1 << 3) != 0,
            opencl: bits & (1 << 4) != 0,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Hash)]
#[repr(u8)]
pub enum SimdWidth {
    Unknown = 0,
    Scalar = 1,
    Sse2 = 2,
    Avx = 3,
    Avx2 = 4,
    Avx512 = 5,
    Neon = 6,
    Sve = 7,
}

impl SimdWidth {
    fn code(self) -> u32 {
        self as u32
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Hash)]
#[repr(u8)]
pub enum OperatingSystem {
    Unknown = 0,
    Linux = 1,
    Windows = 2,
    MacOs = 3,
    Bsd = 4,
    Android = 5,
    Ios = 6,
}

impl OperatingSystem {
    fn code(self) -> u32 {
        self as u32
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Hash)]
pub struct HardwareProfile {
    pub vram: VramClass,
    pub gpu: GpuAcceleration,
    pub simd: SimdWidth,
    pub os: OperatingSystem,
}

impl HardwareProfile {
    pub fn new(
        vram: VramClass,
        gpu: GpuAcceleration,
        simd: SimdWidth,
        os: OperatingSystem,
    ) -> Self {
        Self {
            vram,
            gpu,
            simd,
            os,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Hash, Default)]
pub struct HardwareBucket {
    bits: u32,
}

impl HardwareBucket {
    pub const fn new(bits: u32) -> Self {
        Self { bits }
    }

    pub const fn bits(self) -> u32 {
        self.bits
    }

    pub const fn is_valid(self) -> bool {
        self.bits & RESERVED_MASK == 0
    }

    pub fn try_new(bits: u32) -> Option<Self> {
        let bucket = Self::new(bits);
        bucket.is_valid().then_some(bucket)
    }

    pub fn from_profile(profile: HardwareProfile) -> Self {
        let mut bits = 0u32;
        bits |= profile.vram.code() << VRAM_SHIFT;
        bits |= profile.gpu.bits() << GPU_SHIFT;
        bits |= profile.simd.code() << SIMD_SHIFT;
        bits |= profile.os.code() << OS_SHIFT;
        Self { bits }
    }

    pub fn to_profile(self) -> Option<HardwareProfile> {
        if !self.is_valid() {
            return None;
        }

        let vram = VramClass::try_from((self.bits & VRAM_MASK) >> VRAM_SHIFT).ok()?;
        let simd = SimdWidth::try_from((self.bits & SIMD_MASK) >> SIMD_SHIFT).ok()?;
        let os = OperatingSystem::try_from((self.bits & OS_MASK) >> OS_SHIFT).ok()?;
        let gpu = GpuAcceleration::from_bits((self.bits & GPU_MASK) >> GPU_SHIFT);

        Some(HardwareProfile {
            vram,
            gpu,
            simd,
            os,
        })
    }

    pub fn hamming_distance(self, other: Self) -> u32 {
        (self.bits ^ other.bits).count_ones()
    }

    pub fn similarity(self, other: Self) -> f64 {
        let distance = self.hamming_distance(other) as f64;
        1.0 / (1.0 + distance)
    }
}

impl TryFrom<u32> for VramClass {
    type Error = ();

    fn try_from(value: u32) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::Unknown),
            1 => Ok(Self::Vram256),
            2 => Ok(Self::Vram512),
            3 => Ok(Self::Vram1024),
            4 => Ok(Self::Vram2048),
            5 => Ok(Self::Vram4096),
            6 => Ok(Self::Vram8192),
            7 => Ok(Self::Vram16384),
            8 => Ok(Self::Vram32768),
            _ => Err(()),
        }
    }
}

impl TryFrom<u32> for SimdWidth {
    type Error = ();

    fn try_from(value: u32) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::Unknown),
            1 => Ok(Self::Scalar),
            2 => Ok(Self::Sse2),
            3 => Ok(Self::Avx),
            4 => Ok(Self::Avx2),
            5 => Ok(Self::Avx512),
            6 => Ok(Self::Neon),
            7 => Ok(Self::Sve),
            _ => Err(()),
        }
    }
}

impl TryFrom<u32> for OperatingSystem {
    type Error = ();

    fn try_from(value: u32) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::Unknown),
            1 => Ok(Self::Linux),
            2 => Ok(Self::Windows),
            3 => Ok(Self::MacOs),
            4 => Ok(Self::Bsd),
            5 => Ok(Self::Android),
            6 => Ok(Self::Ios),
            _ => Err(()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn masks_do_not_overlap() {
        assert_eq!(VALID_MASK & RESERVED_MASK, 0);
        assert_eq!(VRAM_MASK & GPU_MASK, 0);
        assert_eq!(VRAM_MASK & SIMD_MASK, 0);
        assert_eq!(VRAM_MASK & OS_MASK, 0);
        assert_eq!(GPU_MASK & SIMD_MASK, 0);
        assert_eq!(GPU_MASK & OS_MASK, 0);
        assert_eq!(SIMD_MASK & OS_MASK, 0);
    }

    #[test]
    fn unknown_bits_are_rejected() {
        let invalid = HardwareBucket::new(1 << 31);
        assert!(!invalid.is_valid());
        assert_eq!(invalid.to_profile(), None);
        assert_eq!(HardwareBucket::try_new(1 << 31), None);
    }

    #[test]
    fn hamming_distance_uses_popcount() {
        let left = HardwareBucket::from_profile(HardwareProfile::new(
            VramClass::Vram4096,
            GpuAcceleration {
                cuda: true,
                metal: false,
                rocm: false,
                vulkan: true,
                opencl: false,
            },
            SimdWidth::Avx2,
            OperatingSystem::Linux,
        ));
        let right = HardwareBucket::from_profile(HardwareProfile::new(
            VramClass::Vram8192,
            GpuAcceleration {
                cuda: false,
                metal: true,
                rocm: false,
                vulkan: false,
                opencl: false,
            },
            SimdWidth::Avx512,
            OperatingSystem::Windows,
        ));

        assert_eq!(
            left.hamming_distance(right),
            (left.bits ^ right.bits).count_ones()
        );
    }

    #[test]
    fn roundtrip_profile() {
        let profile = HardwareProfile::new(
            VramClass::Vram2048,
            GpuAcceleration {
                cuda: true,
                metal: true,
                rocm: false,
                vulkan: false,
                opencl: true,
            },
            SimdWidth::Neon,
            OperatingSystem::MacOs,
        );
        let bucket = HardwareBucket::from_profile(profile);
        assert_eq!(bucket.to_profile(), Some(profile));
    }
}
