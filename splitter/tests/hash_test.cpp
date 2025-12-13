#include <gtest/gtest.h>
#include <fstream>

#include "support/HashUtil.hpp"
#include "support/HashService.hpp"
#include "artifacts/StdHashAlgorithm.hpp"

using namespace splitter;

TEST(HashUtil, BytesDeterministic) {
    std::vector<uint8_t> data = {1, 2, 3, 4, 5};
    auto h1 = HashBytes(data);
    auto h2 = HashBytes(data);
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
    auto hb = HashBytes(data);
    auto hf = HashFile(path);
    EXPECT_FALSE(hf.empty());
    EXPECT_EQ(hb, hf);
    std::remove(path.c_str());
}

TEST(HashUtil, GlobalHashServiceOverride) {
    auto prev = GetGlobalHashService();
    HashService custom(std::make_shared<StdHashAlgorithm>());
    SetGlobalHashService(custom);
    std::vector<uint8_t> data = {1, 2, 3};
    auto h1 = HashBytes(data);
    SetGlobalHashService(prev);  // restore
    auto h2 = HashBytes(data);
    EXPECT_NE(h1, h2);  // Les deux services diffèrent
}
