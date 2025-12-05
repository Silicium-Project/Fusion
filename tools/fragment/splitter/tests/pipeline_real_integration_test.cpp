#include <filesystem>
#include <fstream>
#include <cstdlib>

#include <gtest/gtest.h>

#include "pipeline/PipelineFactory.hpp"
#include "pipeline/PipelineRunner.hpp"

namespace splitter {

namespace fs = std::filesystem;

TEST(PipelineRealIntegration, RunsEndToEndOnCompiledBinary) {
    fs::path tmp_dir = fs::temp_directory_path() / "splitter_real_integration";
    fs::create_directories(tmp_dir);
    fs::path src_path = tmp_dir / "sample.c";
    fs::path bin_path = tmp_dir / "sample_bin";
    fs::path out_dir = tmp_dir / "out";

    {
        std::ofstream src(src_path);
        src << "#include <stdio.h>\n"
               "int main(){\n"
               "  int acc = 0;\n"
               "  for(int i=0;i<4;++i) acc += i;\n"
               "  printf(\"acc=%d\\n\", acc);\n"
               "  return acc;\n"
               "}\n";
    }

    std::string compile_cmd =
        "gcc -O0 -g -no-pie " + src_path.string() + " -o " + bin_path.string() + " >/dev/null 2>&1";
    ASSERT_EQ(0, std::system(compile_cmd.c_str())) << "Compilation du binaire de test échouée";

    PipelineConfig config;
    config.binary_path = BinaryPath(bin_path.string());
    config.output_dir = OutputDir(out_dir.string());
    config.dump_full_disassembly = false;

    auto runner = PipelineFactory::BuildDefault(std::move(config));
    EXPECT_EQ(0, runner->Run());

    fs::path summary = out_dir / "summary.json";
    EXPECT_TRUE(fs::exists(summary));
    if (fs::exists(summary)) {
        EXPECT_GT(fs::file_size(summary), 0u);
    }

    std::error_code ec;
    fs::remove_all(tmp_dir, ec);
}

}  // namespace splitter
