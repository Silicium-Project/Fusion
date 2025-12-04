#include "splitter/partitioning/CallNormalizer.hpp"

#include <cctype>
#include <regex>
#include <sstream>

#include "splitter/support/Env.hpp"

namespace splitter {

std::vector<std::string> DefaultCallNormalizer::GuiPrefixes() const {
    static std::vector<std::string> cached;
    static bool initialized = false;

    if (!initialized) {
        initialized = true;
        if (auto env = GetEnv("SPLITTER_GUI_PREFIXES")) {
            std::string raw(*env);
            std::stringstream ss(raw);
            std::string item;
            while (std::getline(ss, item, ',')) {
                const auto start = item.find_first_not_of(" \t");
                const auto end = item.find_last_not_of(" \t");
                if (start != std::string::npos && end != std::string::npos && end >= start)
                    cached.emplace_back(item.substr(start, end - start + 1));
            }
        }
        if (cached.empty()) {
            cached = {
                "sfRenderWindow_", "sfRenderTexture_", "sfWindow_",
                "sfView_",        "sfSprite_",        "sfKeyboard_",
                "sfMouse_",       "glX",              "SDL_"
            };
        }
    }
    return cached;
}

bool DefaultCallNormalizer::IsGuiSymbol(const std::string& symbol) const {
    const auto& prefixes = GuiPrefixes();
    for (const auto& prefix : prefixes)
        if (symbol.rfind(prefix, 0) == 0)
            return true;
    return false;
}

std::string DefaultCallNormalizer::Normalize(const CallRef& call) const {
    std::string operand = Trim(call.second);
    if (!operand.empty()) {
        auto comment_pos = operand.find('#');
        if (comment_pos != std::string::npos)
            operand = Trim(operand.substr(comment_pos + 1));
    }

    std::string candidate;
    const size_t lt = operand.find('<');
    size_t gt = std::string::npos;
    if (lt != std::string::npos)
        gt = operand.find('>', lt + 1);
    if (lt != std::string::npos && gt != std::string::npos && gt > lt + 1)
        candidate = operand.substr(lt + 1, gt - lt - 1);
    else
        candidate = operand;

    const auto plus_pos = candidate.find('+');
    if (plus_pos != std::string::npos)
        candidate = candidate.substr(0, plus_pos);

    const auto at_pos = candidate.find('@');
    if (at_pos != std::string::npos)
        candidate = candidate.substr(0, at_pos);

    candidate = Trim(candidate);

    auto is_allowed = [](char ch) {
        unsigned char uch = static_cast<unsigned char>(ch);
        return std::isalnum(uch) || ch == '_' || ch == '.' || ch == '-';
    };

    size_t start = 0;
    while (start < candidate.size() && !is_allowed(candidate[start]))
        ++start;
    size_t end = candidate.size();
    while (end > start && !is_allowed(candidate[end - 1]))
        --end;

    if (start >= end)
        candidate.clear();
    else
        candidate = candidate.substr(start, end - start);

    if (!candidate.empty())
        return candidate;

    if (call.first.has_value()) {
        std::ostringstream oss;
        oss << "0x" << std::hex << call.first.value();
        return oss.str();
    }

    return {};
}

}  // namespace splitter
