#include <gtest/gtest.h>
#include <fstream>

#include "splitter/util.hpp"

using namespace splitter;

TEST(HashUtil, BytesDeterministic) {
    std::vector<uint8_t> data = {1, 2, 3, 4, 5};
    auto h1 = hash_bytes(data);
    auto h2 = hash_bytes(data);
    EXPECT_FALSE(h1.empty());
    EXPECT_EQ(h1, h2);
}

TEST(HashUtil, FileHashMatchesBytes) {
    // Création d'un fichier temporaire
    const std::string path = "hash_test.tmp";
    {
        std::ofstream out(path);
        out << "hello";
    }
    std::vector<uint8_t> data = {'h', 'e', 'l', 'l', 'o'};
    auto hb = hash_bytes(data);
    auto hf = hash_file(path);
    EXPECT_FALSE(hf.empty());
    EXPECT_EQ(hb, hf);
    std::remove(path.c_str());
}
