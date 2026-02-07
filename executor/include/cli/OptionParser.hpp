#pragma once

#include "cli/Cli.hpp"

#include <functional>
#include <string>
#include <string_view>
#include <vector>

namespace fragment {

// Petit parseur extensible (Strategy) pour gérer les options CLI.
class OptionParser {
public:
    using FlagHandler = std::function<void(CliOptions&)>;
    using ValueHandler = std::function<void(const std::string&, CliOptions&)>;
    using PassthroughHandler = std::function<void(const std::string&, CliOptions&)>;

    void add_flag(std::string flag, FlagHandler handler);
    void add_value(std::string flag, ValueHandler handler);
    void add_passthrough(PassthroughHandler handler);

    void parse(const std::vector<std::string_view>& args, size_t start_idx, CliOptions& out) const;

private:
    struct OptionSpec {
        std::string flag;
        bool requires_value = false;
        FlagHandler flag_handler;
        ValueHandler value_handler;
    };

    std::vector<OptionSpec> specs_;
    PassthroughHandler passthrough_;
};

}  // namespace fragment
