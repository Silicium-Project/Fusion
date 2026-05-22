#include <gtest/gtest.h>

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

#include "artifacts/PeLibraryScanner.hpp"

namespace fs = std::filesystem;

namespace {

class ScopedEnvVar {
public:
    ScopedEnvVar(std::string key, std::string value) : key_(std::move(key)) {
        if (const char* current = std::getenv(key_.c_str())) {
            had_previous_ = true;
            previous_value_ = current;
        }
        set_value(std::move(value));
    }

    ~ScopedEnvVar() {
        if (had_previous_) {
            set_value(previous_value_);
        } else {
            unset_value();
        }
    }

private:
    void set_value(const std::string& value) {
#ifdef _WIN32
        _putenv_s(key_.c_str(), value.c_str());
#else
        setenv(key_.c_str(), value.c_str(), 1);
#endif
    }

    void unset_value() {
#ifdef _WIN32
        _putenv_s(key_.c_str(), "");
#else
        unsetenv(key_.c_str());
#endif
    }

    std::string key_;
    std::string previous_value_;
    bool had_previous_ = false;
};

fs::path make_temp_path(const std::string& suffix) {
    const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
    return fs::temp_directory_path() / ("splitter_pe_scanner_" + std::to_string(nonce) + suffix);
}

fs::path create_wrapper_script(const std::string& body) {
    const fs::path path = make_temp_path(".sh");
    std::ofstream out(path);
    out << "#!/usr/bin/env bash\n";
    out << "set -euo pipefail\n";
    out << body;
    out.close();
#ifndef _WIN32
    fs::permissions(path,
                    fs::perms::owner_exec | fs::perms::owner_read | fs::perms::owner_write,
                    fs::perm_options::replace);
#endif
    return path;
}

}  // namespace

TEST(PeLibraryScanner, ParsesImportsAndBuildsSymbolIndex) {
    const fs::path wrapper = create_wrapper_script(
        "cat <<'OUT'\n"
        "DLL Name: KERNEL32.dll\n"
        "  0000  ExitProcess\n"
        "DLL Name: USER32.dll\n"
        "  0000  MessageBoxA\n"
        "OUT\n");
    const ScopedEnvVar scoped("SILICIUM_LIB_DETECT_WRAPPER", wrapper.string());

    splitter::PeLibraryScanner scanner;
    const auto libraries = scanner.DetectLibraries("/tmp/demo.exe");
    ASSERT_EQ(libraries.size(), 2u);
    EXPECT_EQ(libraries[0].Name(), "KERNEL32.dll");
    EXPECT_EQ(libraries[1].Name(), "USER32.dll");

    const auto symbols = scanner.BuildSymbolIndex(libraries);
    EXPECT_EQ(symbols.at("ExitProcess"), "KERNEL32.dll");
    EXPECT_EQ(symbols.at("MessageBoxA"), "USER32.dll");

    std::error_code ec;
    fs::remove(wrapper, ec);
}

TEST(PeLibraryScanner, InvalidOutputReturnsNoLibraries) {
    const fs::path wrapper = create_wrapper_script("echo 'not an import table'\n");
    const ScopedEnvVar scoped("SILICIUM_LIB_DETECT_WRAPPER", wrapper.string());

    splitter::PeLibraryScanner scanner;
    const auto libraries = scanner.DetectLibraries("/tmp/demo.exe");
    EXPECT_TRUE(libraries.empty());
    EXPECT_TRUE(scanner.BuildSymbolIndex(libraries).empty());

    std::error_code ec;
    fs::remove(wrapper, ec);
}

TEST(PeLibraryScanner, WrapperFailureReturnsNoLibraries) {
    const fs::path wrapper = create_wrapper_script("exit 1\n");
    const ScopedEnvVar scoped("SILICIUM_LIB_DETECT_WRAPPER", wrapper.string());

    splitter::PeLibraryScanner scanner;
    const auto libraries = scanner.DetectLibraries("/tmp/demo.exe");
    EXPECT_TRUE(libraries.empty());
    EXPECT_TRUE(scanner.BuildSymbolIndex(libraries).empty());

    std::error_code ec;
    fs::remove(wrapper, ec);
}
