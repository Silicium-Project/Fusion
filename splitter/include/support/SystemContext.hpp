#pragma once

#include <filesystem>
#include <memory>
#include <optional>
#include <string>

namespace splitter {

class IShellRunner {
public:
    virtual ~IShellRunner() = default;
    virtual std::string Run(const std::string& cmd) const = 0;
};

class IEnvironment {
public:
    virtual ~IEnvironment() = default;
    virtual std::optional<std::string> Get(const std::string& key) const = 0;
};

class IFileSystem {
public:
    virtual ~IFileSystem() = default;
    virtual bool Exists(const std::filesystem::path& path) const = 0;
    virtual bool IsRegularFile(const std::filesystem::path& path) const = 0;
    virtual bool IsExecutableFile(const std::filesystem::path& path) const = 0;
};

struct SystemContext {
    std::shared_ptr<IShellRunner> shell;
    std::shared_ptr<IEnvironment> env;
    std::shared_ptr<IFileSystem> fs;
};

SystemContext DefaultSystemContext();

}  // namespace splitter
