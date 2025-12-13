#include "core/LibraryInfo.hpp"

namespace splitter {

const std::string& LibraryInfo::Name() const noexcept {
    return name_;
}

void LibraryInfo::SetName(std::string name) noexcept {
    name_ = std::move(name);
}

const std::string& LibraryInfo::Path() const noexcept {
    return path_;
}

void LibraryInfo::SetPath(std::string path) noexcept {
    path_ = std::move(path);
}

const std::string& LibraryInfo::Soname() const noexcept {
    return soname_;
}

void LibraryInfo::SetSoname(std::string soname) noexcept {
    soname_ = std::move(soname);
}

const std::string& LibraryInfo::BuildId() const noexcept {
    return build_id_;
}

void LibraryInfo::SetBuildId(std::string build_id) noexcept {
    build_id_ = std::move(build_id);
}

}  // namespace splitter
