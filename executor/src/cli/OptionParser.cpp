#include "cli/OptionParser.hpp"

#include <stdexcept>

namespace fragment {

    void OptionParser::add_flag(std::string flag, FlagHandler handler) {
        specs_.push_back(OptionSpec{std::move(flag), false, std::move(handler), {}});
    }

    void OptionParser::add_value(std::string flag, ValueHandler handler) {
        specs_.push_back(OptionSpec{std::move(flag), true, {}, std::move(handler)});
    }

    void OptionParser::add_passthrough(PassthroughHandler handler) {
        passthrough_ = std::move(handler);
    }

    void OptionParser::parse(const std::vector<std::string_view>& args, size_t start_idx, CliOptions& out) const {
        for (size_t i = start_idx; i < args.size(); ++i) {
            const std::string current(args[i]);
            bool handled = false;

            for (const auto& spec : specs_) {
                if (current != spec.flag)
                    continue;
                if (spec.requires_value) {
                    if (i + 1 >= args.size())
                        throw std::runtime_error("Option " + spec.flag + " requiert une valeur");
                    spec.value_handler(std::string(args[++i]), out);
                } else
                    spec.flag_handler(out);
                handled = true;
                break;
            }
            if (!handled)
                if (passthrough_) {
                    passthrough_(current, out);
                    handled = true;
                }
            if (!handled)
                throw std::runtime_error("Option inconnue: " + current);
        }
    }

}  // namespace fragment
