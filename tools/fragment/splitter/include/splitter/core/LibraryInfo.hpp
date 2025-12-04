#pragma once

#include <string>

namespace splitter {

class LibraryInfo {
public:
    const std::string& Name() const noexcept { return name_; }
    void SetName(std::string name) noexcept { name_ = std::move(name); }

    const std::string& Path() const noexcept { return path_; }
    void SetPath(std::string path) noexcept { path_ = std::move(path); }

    const std::string& Soname() const noexcept { return soname_; }
    void SetSoname(std::string soname) noexcept { soname_ = std::move(soname); }

    const std::string& BuildId() const noexcept { return build_id_; }
    void SetBuildId(std::string build_id) noexcept { build_id_ = std::move(build_id); }

private:
    std::string name_;
    std::string path_;
    std::string soname_;
    std::string build_id_;
};

}  // namespace splitter
