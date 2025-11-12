#include "splitter/disassembly.hpp"

#include <filesystem>
#include <optional>
#include <regex>
#include <sstream>
#include <utility>

#include "splitter/instruction_analysis.hpp"
#include "splitter/util.hpp"

namespace splitter {

    namespace fs = std::filesystem;

    namespace {
        const std::regex kFunctionPattern("^([0-9a-f]+) <(.+)>:$");
        const std::regex kInstructionPattern("^\\s*([0-9a-f]+):\\s+([0-9a-f ]+)\\s+(\\w+)\\s*(.*)$");

        Function make_function(const std::smatch& match) {
            Function func;

            func.start_addr = std::stoull(match[1].str(), nullptr, 16);
            func.end_addr = func.start_addr;
            func.name = match[2].str();
            return func;
        }

        AsmInstruction make_instruction(const std::smatch& match) {
            AsmInstruction inst;

            inst.address = std::stoull(match[1].str(), nullptr, 16);
            inst.bytes = match[2].str();
            inst.opcode = match[3].str();
            inst.operands = trim(match[4].str());
            analyze_instruction(inst);
            return inst;
        }

        void flush_current(std::vector<Function>& functions, std::optional<Function>& current) {
            if (!current.has_value())
                return;
            functions.push_back(*current);
            current.reset();
        }

        bool start_new_function(const std::string& line,
                                std::optional<Function>& current,
                                std::vector<Function>& functions) {
            std::smatch match;

            if (!std::regex_match(line, match, kFunctionPattern))
                return false;
            flush_current(functions, current);
            current = make_function(match);
            return true;
        }

        void append_instruction(const std::string& line, std::optional<Function>& current) {
            if (!current.has_value())
                return;

            std::smatch match;

            if (!std::regex_match(line, match, kInstructionPattern))
                return;
            AsmInstruction inst = make_instruction(match);
            current->instructions.push_back(inst);
            current->end_addr = inst.address;
        }
    }  // namespace

    Disassembler::Disassembler(std::string binary_path)
    : binary_path_(std::move(binary_path)) {}

    std::vector<Function> Disassembler::parse_objdump_output(const std::string& output) {
        std::vector<Function> functions;
        std::optional<Function> current;
        std::istringstream stream(output);
        std::string line;

        while (std::getline(stream, line)) {
            if (start_new_function(line, current, functions))
                continue;
            append_instruction(line, current);
        }

        flush_current(functions, current);
        return functions;
    }

    std::pair<std::vector<Function>, std::string> Disassembler::run() const {
        if (!fs::exists(binary_path_))
            throw std::runtime_error("Binaire introuvable: " + binary_path_);

        std::string cmd = "objdump -d -M intel " + binary_path_;
        std::string disasm_output;

        try {
            disasm_output = exec_command(cmd);
        } catch (const std::exception&) {
            throw std::runtime_error("Désassemblage échoué. Installez binutils: apt-get install binutils");
        }

        auto functions = parse_objdump_output(disasm_output);
        return {functions, disasm_output};
    }

    std::vector<Function> parse_objdump_output(const std::string& output) {
        return Disassembler::parse_objdump_output(output);
    }

    std::pair<std::vector<Function>, std::string> disassemble_binary(const std::string& binary_path) {
        Disassembler disassembler(binary_path);
        return disassembler.run();
    }

}  // namespace splitter
