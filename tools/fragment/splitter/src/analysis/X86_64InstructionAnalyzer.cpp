#include "analysis/X86_64InstructionAnalyzer.hpp"

#include <algorithm>
#include <cctype>
#include <regex>
#include <sstream>
#include <unordered_map>
#include <string>

#include "arch/ArchitectureProfile.hpp"
#include "arch/RegisterCatalog.hpp"
#include "support/StringUtil.hpp"

namespace splitter {

namespace {

struct ParsedOperand {
    std::string raw;
    bool is_memory = false;
    bool is_register = false;
    bool is_immediate = false;
    std::vector<std::string> registers;
};

class OperandParser {
public:
    static std::vector<ParsedOperand> ParseAll(const std::string& operands) {
        std::vector<ParsedOperand> parsed_operands;
        std::stringstream ss(operands);
        std::string raw;
        while (std::getline(ss, raw, ','))
            parsed_operands.push_back(ParseSingle(raw));

        parsed_operands.erase(
            std::remove_if(parsed_operands.begin(), parsed_operands.end(),
                           [](const ParsedOperand& op) { return op.raw.empty(); }),
            parsed_operands.end());
        return parsed_operands;
    }

private:
    static ParsedOperand ParseSingle(const std::string& operand) {
        ParsedOperand parsed;
        parsed.raw = Trim(operand);
        if (parsed.raw.empty())
            return parsed;

        std::string lowered = ToLower(parsed.raw);
        auto mem_keyword = ToLower(std::string(ArchitectureProfile::Instance().MemoryKeyword()));
        bool has_brackets = lowered.find('[') != std::string::npos;
        bool has_keyword = !mem_keyword.empty() && lowered.find(mem_keyword) != std::string::npos;
        parsed.is_memory = has_brackets || has_keyword;
        parsed.is_immediate = IsImmediate(lowered);
        ExtractRegisters(lowered, parsed.registers);

        if (!parsed.is_memory && parsed.registers.size() == 1 && lowered == parsed.registers.front())
            parsed.is_register = true;
        return parsed;
    }

    static std::string ToLower(std::string text) {
        std::transform(text.begin(), text.end(), text.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        return text;
    }

    static bool IsImmediate(const std::string& value) {
        if (value.empty())
            return false;
        if (!value.rfind("0x", 0))
            return true;
        auto is_digit = [](unsigned char c) { return !!std::isdigit(c); };
        if (value[0] == '-' || value[0] == '+')
            return value.size() > 1
                   && std::all_of(value.begin() + 1, value.end(),
                                  [&](char c) { return is_digit(static_cast<unsigned char>(c)); });
        return std::all_of(value.begin(), value.end(),
                           [&](char c) { return is_digit(static_cast<unsigned char>(c)); });
    }

    static void ExtractRegisters(const std::string& lowered, std::vector<std::string>& out) {
        const auto& catalog = RegisterCatalog::Instance();
        for (std::size_t idx = 0; idx < lowered.size();) {
            unsigned char ch = static_cast<unsigned char>(lowered[idx]);
            if (std::isalpha(ch)) {
                std::size_t start = idx;
                while (idx < lowered.size()) {
                    unsigned char inner = static_cast<unsigned char>(lowered[idx]);
                    if (!std::isalnum(inner) && inner != '_')
                        break;
                    ++idx;
                }
                std::string token = lowered.substr(start, idx - start);
                if (catalog.Contains(token) && std::find(out.begin(), out.end(), token) == out.end())
                    out.push_back(std::move(token));
            } else
                ++idx;
        }
    }
};

enum class OpcodeId : std::uint8_t {
    Cmp,
    Test,
    Push,
    Pop,
    Call,
    Callq,
    Ret,
    Jump,
    Other
};

using OpcodeLookupMap =
    std::unordered_map<std::string_view, OpcodeId, std::hash<std::string_view>, std::equal_to<>>;

const OpcodeLookupMap& OpcodeLookup() {
    static const OpcodeLookupMap map = [] {
        OpcodeLookupMap table;
        table.reserve(26);
        table.emplace("cmp", OpcodeId::Cmp);
        table.emplace("test", OpcodeId::Test);
        table.emplace("push", OpcodeId::Push);
        table.emplace("pop", OpcodeId::Pop);
        table.emplace("call", OpcodeId::Call);
        table.emplace("callq", OpcodeId::Callq);
        table.emplace("ret", OpcodeId::Ret);
        table.emplace("jmp", OpcodeId::Jump);
        table.emplace("je", OpcodeId::Jump);
        table.emplace("jne", OpcodeId::Jump);
        table.emplace("jg", OpcodeId::Jump);
        table.emplace("jge", OpcodeId::Jump);
        table.emplace("jl", OpcodeId::Jump);
        table.emplace("jle", OpcodeId::Jump);
        table.emplace("ja", OpcodeId::Jump);
        table.emplace("jae", OpcodeId::Jump);
        table.emplace("jb", OpcodeId::Jump);
        table.emplace("jbe", OpcodeId::Jump);
        table.emplace("jz", OpcodeId::Jump);
        table.emplace("jnz", OpcodeId::Jump);
        table.emplace("js", OpcodeId::Jump);
        table.emplace("jns", OpcodeId::Jump);
        table.emplace("jo", OpcodeId::Jump);
        table.emplace("jno", OpcodeId::Jump);
        table.emplace("jp", OpcodeId::Jump);
        table.emplace("jnp", OpcodeId::Jump);
        return table;
    }();
    return map;
}

OpcodeId ClassifyOpcode(std::string_view opcode) {
    const auto& map = OpcodeLookup();
    auto it = map.find(opcode);
    if (it != map.end())
        return it->second;
    return OpcodeId::Other;
}

const std::regex& JumpTargetRegex() {
    static const std::regex pattern("(?:0x)?([0-9a-f]+)", std::regex::icase | std::regex::optimize);
    return pattern;
}

}  // namespace

const X86_64InstructionAnalyzer& X86_64InstructionAnalyzer::Instance() {
    static const X86_64InstructionAnalyzer analyzer;
    return analyzer;
}

bool X86_64InstructionAnalyzer::IsJumpOpcode(std::string_view opcode) {
    return ClassifyOpcode(opcode) == OpcodeId::Jump;
}

bool X86_64InstructionAnalyzer::IsCallOpcode(std::string_view opcode) {
    auto id = ClassifyOpcode(opcode);
    return id == OpcodeId::Call || id == OpcodeId::Callq;
}

bool X86_64InstructionAnalyzer::IsStackOpcode(std::string_view opcode) {
    auto id = ClassifyOpcode(opcode);
    switch (id) {
        case OpcodeId::Push:
        case OpcodeId::Pop:
        case OpcodeId::Call:
        case OpcodeId::Callq:
        case OpcodeId::Ret:
            return true;
        default:
            return false;
    }
}

bool X86_64InstructionAnalyzer::IsCallClobberedReg(std::string_view reg) {
    return Register::IsCallClobbered(reg);
}

void X86_64InstructionAnalyzer::AnalyzeInstruction(Instruction& inst) const {
    const OpcodeId opcode_id = ClassifyOpcode(inst.Opcode());

    if (IsJumpOpcode(inst.Opcode())) {
        std::smatch match;
        if (std::regex_search(inst.Operands(), match, JumpTargetRegex())) {
            inst.SetTargetAddr(std::stoull(match[1].str(), nullptr, 16));
            inst.SetIsJump(true);
        }
    }

    if (IsCallOpcode(inst.Opcode())) {
        std::smatch match;
        if (std::regex_search(inst.Operands(), match, JumpTargetRegex()))
            inst.SetTargetAddr(std::stoull(match[1].str(), nullptr, 16));
        inst.SetIsCall(true);
    }

    auto parsed = OperandParser::ParseAll(inst.Operands());
    if (!parsed.empty()) {
        bool first_operand = true;
        for (const auto& operand : parsed) {
            if (operand.is_memory)
                inst.SetIsMemory(true);
            if (!first_operand || operand.is_memory) {
                for (const auto& reg : operand.registers)
                    inst.Reads().insert(reg);
            }
            first_operand = false;
        }

        const auto& dest = parsed.front();
        auto should_skip_destination = [&](OpcodeId id) {
            switch (id) {
                case OpcodeId::Cmp:
                case OpcodeId::Test:
                case OpcodeId::Push:
                case OpcodeId::Call:
                case OpcodeId::Callq:
                case OpcodeId::Jump:
                    return true;
                default:
                    return false;
            }
        };

        if (!should_skip_destination(opcode_id)) {
            if (dest.is_memory) {
                inst.SetIsMemory(true);
                inst.SetWritesMemory(true);
            } else if (!dest.registers.empty()) {
                inst.Writes().insert(dest.registers.front());
            }
        }
    }

    if (IsStackOpcode(inst.Opcode())) {
        auto stack_reg = ArchitectureProfile::Instance().StackPointer();
        inst.Reads().insert(stack_reg);
        inst.Writes().insert(stack_reg);
    }

    if (IsCallOpcode(inst.Opcode())) {
        for (const auto& reg : Register::All())
            if (reg.IsCallClobbered())
                inst.Writes().insert(std::string(reg.Name()));
    }
}

bool X86_64InstructionAnalyzer::AnalyzeFunctionLoops(Function& func) const {
    func.SetIsLoop(false);
    func.Loops().clear();

    for (const auto& inst : func.Instructions()) {
        if (inst.IsJump() && inst.TargetAddr().has_value()) {
            LoopInfo info;
            info.source_addr = inst.Address();
            info.target_addr = inst.TargetAddr().value();
            info.backward = info.target_addr <= inst.Address();

            if (info.backward) {
                func.SetIsLoop(true);
                func.Loops().push_back(info);
            }
        }
    }
    return func.IsLoop();
}

LoopAnalysis X86_64InstructionAnalyzer::DetectLoopPatterns(const Function& func) const {
    if (!func.IsLoop())
        return {false, "pas de boucle"};

    bool writes_memory = false;
    for (const auto& inst : func.Instructions())
        if (inst.WritesMemory()) {
            writes_memory = true;
            break;
        }

    std::ostringstream reason;
    if (!func.Loops().empty()) {
        reason << "boucle ";
        const std::size_t preview = std::min<std::size_t>(3, func.Loops().size());
        for (std::size_t idx = 0; idx < preview; ++idx) {
            const auto& loop = func.Loops()[idx];
            reason << "0x" << std::hex << loop.source_addr << "->0x" << loop.target_addr;
            if (idx + 1 < preview)
                reason << ", ";
        }
        if (func.Loops().size() > preview)
            reason << ", ...";
    } else {
        reason << "structure de boucle inconnue";
    }

    if (writes_memory) {
        reason << " (memory dependencies)";
        return {false, reason.str()};
    }

    reason << " (no memory writes)";
    return {true, reason.str()};
}

}  // namespace splitter
