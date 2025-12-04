#include "splitter/support/HashUtil.hpp"

#include <fstream>

namespace splitter {

namespace {
HashService& GlobalService() {
    static HashService service;
    return service;
}
}  // namespace

std::string HashBytes(const std::vector<uint8_t>& data) {
    return GlobalService().HashBytes(data);
}

std::string HashFile(const std::string& path) {
    return GlobalService().HashFile(path);
}

std::string HashString(const std::string& data) {
    return GlobalService().HashString(data);
}

void SetGlobalHashService(HashService service) {
    GlobalService() = std::move(service);
}

const HashService& GetGlobalHashService() {
    return GlobalService();
}

}  // namespace splitter
