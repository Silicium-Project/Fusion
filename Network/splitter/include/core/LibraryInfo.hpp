#pragma once

#include <string>

namespace splitter {

class LibraryInfo {
public:
    const std::string& Name() const noexcept;
    void SetName(std::string name) noexcept;

    const std::string& Path() const noexcept;
    void SetPath(std::string path) noexcept;

    const std::string& Soname() const noexcept;
    void SetSoname(std::string soname) noexcept;

    const std::string& BuildId() const noexcept;
    void SetBuildId(std::string build_id) noexcept;

private:
    std::string name_;
    std::string path_;
    std::string soname_;
    std::string build_id_;
};

}  // namespace splitter
