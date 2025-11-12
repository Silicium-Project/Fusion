#include "splitter/instruction_analysis.hpp"
#include "splitter/util.hpp"

#include <algorithm>
#include <cctype>
#include <iomanip>
#include <sstream>
#include <unordered_map>

namespace splitter {

    struct ParsedOperand {
        std::string raw;
        bool is_memory = false;
        bool is_register = false;
        bool is_immediate = false;
        std::vector<std::string> registers;
    };

    namespace {

        class OperandParser {
        public:
            static std::vector<ParsedOperand> parse_all(const std::string& operands) {
                std::vector<ParsedOperand> parsed_operands;
                std::stringstream ss(operands);
                std::string raw;

                while (std::getline(ss, raw, ','))
                    parsed_operands.push_back(parse_single(raw));

                parsed_operands.erase(
                    std::remove_if(parsed_operands.begin(), parsed_operands.end(),
                                   [](const ParsedOperand& op) { return op.raw.empty(); }),
                    parsed_operands.end());
                return parsed_operands;
            }

        private:
            static ParsedOperand parse_single(const std::string& operand) {
                ParsedOperand parsed;
                parsed.raw = trim(operand);

                if (parsed.raw.empty())
                    return parsed;

                std::string lowered = to_lower(parsed.raw);
                auto mem_keyword = to_lower(std::string(ArchitectureProfile::instance().memory_keyword()));
                bool has_brackets = lowered.find('[') != std::string::npos;
                bool has_keyword = !mem_keyword.empty() && lowered.find(mem_keyword) != std::string::npos;
                parsed.is_memory = has_brackets || has_keyword;
                parsed.is_immediate = is_immediate(lowered);
                extract_registers(lowered, parsed.registers);

                if (!parsed.is_memory && parsed.registers.size() == 1
                 && lowered == parsed.registers.front())
                    parsed.is_register = true;

                return parsed;
            }

            static std::string to_lower(std::string text) {
                std::transform(text.begin(), text.end(), text.begin(), [](unsigned char c) {
                    return static_cast<char>(std::tolower(c));
                });
                return text;
            }

            static bool is_immediate(const std::string& value) {
                if (value.empty())
                    return false;
                if (value.rfind("0x", 0) == 0)
                    return true;
                auto is_digit = [](unsigned char c) { return std::isdigit(c) != 0; };
                if (value[0] == '-' || value[0] == '+')
                    return value.size() > 1
                        && std::all_of(value.begin() + 1, value.end(),
                                       [&](char c) { return is_digit(static_cast<unsigned char>(c)); });
                return std::all_of(value.begin(), value.end(),
                                   [&](char c) { return is_digit(static_cast<unsigned char>(c)); });
            }

            static void extract_registers(const std::string& lowered, std::vector<std::string>& out) {
                const auto& catalog = RegisterCatalog::instance();
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
                        if (catalog.contains(token)
                         && std::find(out.begin(), out.end(), token) == out.end())
                            out.push_back(std::move(token));
                    } else
                        ++idx;
                }
            }
        };

        using OpcodeLookupMap = std::unordered_map<std::string_view, OpcodeId, std::hash<std::string_view>, std::equal_to<>>;

        const OpcodeLookupMap& opcode_lookup() {
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

        const std::regex& jump_target_regex() {
            static const std::regex pattern("0x([0-9a-f]+)", std::regex::icase | std::regex::optimize);
            return pattern;
        }

    }  // namespace

    InstructionAnalyzer& InstructionAnalyzer::instance() {
        static InstructionAnalyzer analyzer;
        return analyzer;
    }

    OpcodeId classify_opcode(std::string_view opcode) {
        const auto& map = opcode_lookup();
        auto it = map.find(opcode);

        if (it != map.end())
            return it->second;
        return OpcodeId::Other;
    }

    bool is_jump_opcode(std::string_view opcode) {
        return classify_opcode(opcode) == OpcodeId::Jump;
    }

    bool is_call_opcode(std::string_view opcode) {
        auto id = classify_opcode(opcode);
        return id == OpcodeId::Call || id == OpcodeId::Callq;
    }

    bool is_stack_opcode(std::string_view opcode) {
        auto id = classify_opcode(opcode);
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

    bool is_call_clobbered_reg(std::string_view reg) {
        return Register::is_call_clobbered(reg);
    }

    void InstructionAnalyzer::record_register_reads(const ParsedOperand& operand, AsmInstruction& inst) const {
        for (const auto& reg : operand.registers)
            inst.reads.insert(reg);
    }

    void InstructionAnalyzer::mark_destination_write(const ParsedOperand& dest, OpcodeId opcode_id,
                                                     AsmInstruction& inst) const {
        if (should_skip_destination(opcode_id))
            return;

        if (dest.is_memory) {
            inst.is_memory = true;
            inst.writes_memory = true;
            return;
        }

        if (!dest.registers.empty())
            inst.writes.insert(dest.registers.front());
    }

    void InstructionAnalyzer::mark_control_flow(AsmInstruction& inst, bool is_jump) const {
        std::smatch match;

        if (!std::regex_search(inst.operands, match, jump_target_regex()))
            return;

        inst.target_addr = std::stoull(match[1].str(), nullptr, 16);

        if (is_jump)
            inst.is_jump = true;
        else
            inst.is_call = true;
    }

    void InstructionAnalyzer::parse_operands(const std::string& operands, OpcodeId opcode_id,
                                             AsmInstruction& inst) const {
        auto parsed = OperandParser::parse_all(operands);

        if (parsed.empty())
            return;

        bool first_operand = true;
        for (const auto& operand : parsed) {
            if (operand.is_memory)
                inst.is_memory = true;

            if (!first_operand || operand.is_memory)
                record_register_reads(operand, inst);

            first_operand = false;
        }

        mark_destination_write(parsed.front(), opcode_id, inst);
    }

    void InstructionAnalyzer::mark_stack_effect(AsmInstruction& inst, OpcodeId opcode_id) const {
        switch (opcode_id) {
            case OpcodeId::Push:
            case OpcodeId::Pop:
            case OpcodeId::Call:
            case OpcodeId::Callq:
            case OpcodeId::Ret:
                break;
            default:
                return;
        }

        auto stack_reg = ArchitectureProfile::instance().stack_pointer();
        inst.reads.insert(stack_reg);
        inst.writes.insert(stack_reg);
    }

    void InstructionAnalyzer::mark_call_clobbers(AsmInstruction& inst, OpcodeId opcode_id) const {
        switch (opcode_id) {
            case OpcodeId::Call:
            case OpcodeId::Callq:
                break;
            default:
                return;
        }

        for (const auto& reg : Register::all())
            if (reg.is_call_clobbered())
                inst.writes.insert(std::string(reg.name()));
    }

    bool InstructionAnalyzer::should_skip_destination(OpcodeId opcode_id) const {
        switch (opcode_id) {
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
    }

    void InstructionAnalyzer::analyze_instruction(AsmInstruction& inst) const {
        const OpcodeId opcode_id = classify_opcode(inst.opcode);

        if (is_jump_opcode(inst.opcode))
            mark_control_flow(inst, true);

        if (is_call_opcode(inst.opcode))
            mark_control_flow(inst, false);

        parse_operands(inst.operands, opcode_id, inst);
        mark_stack_effect(inst, opcode_id);
        mark_call_clobbers(inst, opcode_id);
    }

    bool InstructionAnalyzer::analyze_function_loops(Function& func) const {
        func.is_loop = false;
        func.loops.clear();

        for (const auto& inst : func.instructions)
            if (inst.is_jump && inst.target_addr.has_value()) {
                LoopDescriptor descriptor;
                descriptor.source_addr = inst.address;
                descriptor.target_addr = inst.target_addr.value();
                descriptor.backward = descriptor.target_addr <= inst.address;

                if (descriptor.backward) {
                    func.is_loop = true;
                    func.loops.push_back(descriptor);
                }
            }

        return func.is_loop;
    }

    LoopAnalysis InstructionAnalyzer::detect_loop_patterns(const Function& func) const {
        if (!func.is_loop)
            return {false, "pas de boucle"};

        bool writes_memory = false;
        for (const auto& inst : func.instructions)
            if (inst.writes_memory) {
                writes_memory = true;
                break;
            }

        std::ostringstream reason;
        if (!func.loops.empty()) {
            reason << "boucle ";
            const std::size_t preview = std::min<std::size_t>(3, func.loops.size());
            for (std::size_t idx = 0; idx < preview; ++idx) {
                const auto& loop = func.loops[idx];
                reason << "0x" << std::hex << loop.source_addr
                       << "->0x" << loop.target_addr;
                if (idx + 1 < preview)
                    reason << ", ";
            }
            if (func.loops.size() > preview)
                reason << ", ...";
        } else
            reason << "structure de boucle inconnue";

        if (writes_memory) {
            reason << " (memory dependencies)";
            return {false, reason.str()};
        }

        reason << " (no memory writes)";
        return {true, reason.str()};
    }

    void analyze_instruction(AsmInstruction& inst) {
        InstructionAnalyzer::instance().analyze_instruction(inst);
    }

    bool analyze_function_loops(Function& func) {
        return InstructionAnalyzer::instance().analyze_function_loops(func);
    }

    LoopAnalysis detect_loop_patterns(const Function& func) {
        return InstructionAnalyzer::instance().detect_loop_patterns(func);
    }

}  // namespace splitter
