#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "analysis/IInstructionAnalyzer.hpp"
#include "core/Function.hpp"
#include "partitioning/BinaryExtractor.hpp"
#include "partitioning/Partitioner.hpp"

using namespace splitter;

namespace {

class FakeAnalyzer : public IInstructionAnalyzer {
public:
    void AnalyzeInstruction(Instruction&) const override {}
    bool AnalyzeFunctionLoops(Function& func) const override {
        func.SetIsLoop(false);
        return false;
    }
    LoopAnalysis DetectLoopPatterns(const Function&) const override {
        return {false, "none"};
    }
};

class FakeExtractor : public BinaryExtractor {
public:
    std::vector<uint8_t> ExtractSegment(const std::string&, uint64_t, uint64_t) const override {
        return {0x01, 0x02};
    }
    std::vector<MemorySegment> ExtractDataSections(const std::string&) const override {
        return {};
    }
};

Function MakeFunc(std::string name, uint64_t start, uint64_t end,
                  const std::vector<std::pair<std::string, bool>>& insts) {
    Function f;
    f.SetName(std::move(name));
    f.SetStartAddr(start);
    f.SetEndAddr(end);
    for (auto&& [op, is_call] : insts) {
        Instruction i;
        i.SetOpcode(op);
        i.SetOperands("");
        i.SetIsCall(is_call);
        f.Instructions().push_back(i);
    }
    return f;
}

}  // namespace

TEST(Partitioner, BuildsPartitionsAndDeps) {
    auto analyzer = std::make_shared<FakeAnalyzer>();
    auto extractor = std::make_shared<FakeExtractor>();
    Partitioner partitioner(BinaryPath("dummy.bin"), analyzer, extractor);

    std::vector<Function> funcs;
    // Two functions, first calls second (dependency), both named without underscores.
    funcs.push_back(MakeFunc("main", 0x1000, 0x1100, {{"call", true}}));
    funcs.back().Instructions().back().SetTargetAddr(0x2000);
    funcs.push_back(MakeFunc("helper", 0x2000, 0x2100, {}));

    auto parts = partitioner.Run(funcs);
    ASSERT_EQ(parts.size(), 2u);

    const Partition& p0 = parts[0];
    const Partition& p1 = parts[1];

    EXPECT_EQ(p0.Id(), "func_0_main");
    EXPECT_EQ(p1.Id(), "func_1_helper");

    // Dependency main -> helper
    ASSERT_EQ(p0.Dependencies().size(), 1u);
    EXPECT_EQ(p0.Dependencies().front(), p1.Id());
    // Parent for helper is main
    ASSERT_EQ(p1.Parents().size(), 1u);
    EXPECT_EQ(p1.Parents().front(), p0.Id());

    // External inputs on helper should be empty (no parents), main should also be empty
    EXPECT_TRUE(p0.ExternalInputs().empty());
    EXPECT_TRUE(p1.ExternalInputs().empty());

    // Raw bytes filled by extractor stub
    EXPECT_FALSE(p0.RawBytes().empty());
    EXPECT_FALSE(p1.RawBytes().empty());
}
