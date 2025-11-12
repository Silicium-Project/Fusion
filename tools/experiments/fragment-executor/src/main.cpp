#include "fragment/runner.hpp"

int main(int argc, char** argv) {
    std::vector<std::string_view> args;
    args.reserve(static_cast<size_t>(argc));
    for (int i = 0; i < argc; ++i)
        args.emplace_back(argv[i]);

    return fragment::run_cli(args);
}
