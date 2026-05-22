#include <gtest/gtest.h>

#include "support/FlatMap.hpp"

using namespace splitter;

TEST(FlatMap, InsertFindAndOrder) {
    FlatMap<std::string, int> map;
    EXPECT_TRUE(map.insert("b", 2));
    EXPECT_TRUE(map.insert("a", 1));
    EXPECT_FALSE(map.insert("a", 3));  // déjà présent

    auto it = map.find("a");
    ASSERT_NE(it, map.end());
    EXPECT_EQ(it->second, 1);

    std::vector<std::string> keys;
    for (auto& kv : map)
        keys.push_back(kv.first);
    EXPECT_EQ(keys, (std::vector<std::string>{"a", "b"}));
}

TEST(FlatMap, OperatorBracketCreatesEntry) {
    FlatMap<std::string, int> map;
    map["x"] = 42;
    EXPECT_TRUE(map.contains("x"));
    EXPECT_EQ(map.at("x"), 42);
}
