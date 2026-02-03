#include "cli/ArgParser.hpp"
#include "cli/OptionParser.hpp"

#include <map>
#include <stdexcept>

namespace fragment {

namespace {

uint64_t parse_input_value(const std::string& token) {
    if (token.size() > 2 && (token.substr(0, 2) == "0x" || token.substr(0, 2) == "0X"))
        return std::stoull(token, nullptr, 16);
    return std::stoull(token);
}

void add_input_argument(const std::string& arg, std::map<std::string, uint64_t>& inputs) {
    size_t eq_pos = arg.find('=');
    if (eq_pos == std::string::npos)
        throw std::runtime_error("Argument --input invalide: " + arg);
    std::string reg = arg.substr(0, eq_pos);
    std::string value_token = arg.substr(eq_pos + 1);
    inputs[reg] = parse_input_value(value_token);
}

}  // namespace

CliOptions parse_arguments(const std::vector<std::string_view>& args) {
    CliOptions opts;
    OptionParser parser;

    parser.add_flag("--native", [](CliOptions& o) { o.native_mode = true; });
    parser.add_flag("--native-force", [](CliOptions& o) { o.native_mode = true; o.force_native = true; });
    parser.add_flag("--skip-memory-check", [](CliOptions& o) { o.skip_memory_check = true; });
    parser.add_flag("--help", [](CliOptions&) { throw std::runtime_error("Option --help demandée"); });

    parser.add_value("--summary", [](const std::string& v, CliOptions& o) { o.summary_file = v; });
    parser.add_value("--log", [](const std::string& v, CliOptions& o) { o.log_path = v; });
    parser.add_value("--input", [](const std::string& v, CliOptions& o) { add_input_argument(v, o.inputs); });

    parser.add_passthrough([](const std::string& v, CliOptions& o) { o.asm_files.push_back(v); });

    parser.parse(args, 1, opts);
    return opts;
}

}  // namespace fragment
