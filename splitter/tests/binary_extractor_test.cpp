#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>

#include "partitioning/BinaryExtractor.hpp"

namespace splitter {
namespace {

std::filesystem::path write_temp_file(const std::string& name, const std::string& content) {
    auto path = std::filesystem::temp_directory_path() / name;
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out << content;
    return path;
}

}  // namespace

TEST(BinaryExtractor, HandlesMissingSectionsGracefully) {
    BinaryExtractor extractor;
    auto path = write_temp_file("splitter_empty.bin", "");

    auto bytes = extractor.ExtractSegment(path.string(), 0x1000, 0x1010);
    EXPECT_TRUE(bytes.empty());

    auto segments = extractor.ExtractDataSections(path.string());
    EXPECT_TRUE(segments.empty());
}

}  // namespace splitter
