#include <gtest/gtest.h>

#include "core/Memory.hpp"
#include "worker/state/MemoryLut.hpp"

using worker::MemoryLut;
using worker::MemorySnapshot;

TEST(MemoryLut, IgnoreEmptyPatch) {
    MemoryLut lut;
    fragment::MemoryPatch empty_patch;
    empty_patch.address = 0x1000;
    empty_patch.after.clear();

    lut.apply_patch(empty_patch);
    EXPECT_TRUE(lut.chunks().empty());
}

TEST(MemoryLut, SeedApplyPatchAndSnapshot) {
    MemoryLut lut;
    MemorySnapshot base;
    base.address = 0x2000;
    base.bytes = {0xAA, 0xBB};
    lut.seed({base});

    fragment::MemoryPatch patch;
    patch.address = 0x3000;
    patch.after = {0x01, 0x02, 0x03};
    lut.apply_patch(patch);

    const auto snapshots = lut.snapshot();
    ASSERT_EQ(2u, snapshots.size());
    EXPECT_EQ(0x2000u, snapshots[0].address);
    EXPECT_EQ(base.bytes, snapshots[0].bytes);
    EXPECT_EQ(0x3000u, snapshots[1].address);
    EXPECT_EQ(patch.after, snapshots[1].bytes);
}
