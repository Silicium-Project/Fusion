#include "support/HashUtil.hpp"

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

HashUtilService::HashUtilService(HashService service)
: service_(std::move(service)) {}

std::string HashUtilService::HashBytes(const std::vector<uint8_t>& data) const {
    return service_.HashBytes(data);
}

std::string HashUtilService::HashFile(const std::string& path) const {
    return service_.HashFile(path);
}

std::string HashUtilService::HashString(const std::string& data) const {
    return service_.HashString(data);
}

}  // namespace splitter
