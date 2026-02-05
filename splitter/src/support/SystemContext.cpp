#include "support/SystemContext.hpp"

#include <filesystem>

#include "support/Env.hpp"
#include "support/ShellCommand.hpp"

namespace splitter {
namespace fs = std::filesystem;

namespace {

class DefaultShellRunner : public IShellRunner {
public:
    std::string Run(const std::string& cmd) const override {
        return ExecCommand(cmd);
    }
};

class DefaultEnvironment : public IEnvironment {
public:
    std::optional<std::string> Get(const std::string& key) const override {
        return GetEnv(key);
    }
};

class DefaultFileSystem : public IFileSystem {
public:
    bool Exists(const fs::path& path) const override {
        std::error_code ec;
        return fs::exists(path, ec);
    }

    bool IsRegularFile(const fs::path& path) const override {
        std::error_code ec;
        return fs::is_regular_file(path, ec);
    }

    bool IsExecutableFile(const fs::path& path) const override {
        std::error_code ec;
        if (!fs::is_regular_file(path, ec))
            return false;
#ifdef _WIN32
        (void)ec;
        return true;
#else
        auto path_perms = fs::status(path, ec).permissions();
        if (ec)
            return false;
        using perms = fs::perms;
        return (path_perms & perms::owner_exec) != perms::none
            || (path_perms & perms::group_exec) != perms::none
            || (path_perms & perms::others_exec) != perms::none;
#endif
    }
};

}  // namespace

SystemContext DefaultSystemContext() {
    SystemContext ctx;
    ctx.shell = std::make_shared<DefaultShellRunner>();
    ctx.env = std::make_shared<DefaultEnvironment>();
    ctx.fs = std::make_shared<DefaultFileSystem>();
    return ctx;
}

}  // namespace splitter
