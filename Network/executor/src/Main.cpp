#include "runtime/Runner.hpp"

int main(int argc, char** argv) {
    std::vector<std::string> raw_args;
    raw_args.reserve(static_cast<size_t>(argc));
    for (int i = 0; i < argc; ++i)
        raw_args.emplace_back(argv[i]);

    std::vector<std::string_view> args;
    args.reserve(raw_args.size());
    for (const auto& arg : raw_args)
        args.emplace_back(arg);

    return fragment::run_cli(args, raw_args);
}
