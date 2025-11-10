#include "splitter/disassembly.hpp"

#include <filesystem>
#include <fstream>
#include <regex>
#include <sstream>

#include "splitter/instruction_analysis.hpp"
#include "splitter/util.hpp"

namespace splitter {

namespace fs = std::filesystem;

std::vector<Function> parse_objdump_output(const std::string& output) {
    std::vector<Function> functions;
    Function* current_function = nullptr;

    std::regex func_pattern("^([0-9a-f]+) <(.+)>:$");
    std::regex inst_pattern("^\\s*([0-9a-f]+):\\s+([0-9a-f ]+)\\s+(\\w+)\\s*(.*)$");

    std::istringstream stream(output);
    std::string line;

    while (std::getline(stream, line)) {
        std::smatch match;
        if (std::regex_match(line, match, func_pattern)) {
            if (current_function) {
                functions.push_back(*current_function);
                delete current_function;
            }
            uint64_t addr = std::stoull(match[1].str(), nullptr, 16);
            std::string name = match[2].str();
            current_function = new Function();
            current_function->name = name;
            current_function->start_addr = addr;
            current_function->end_addr = addr;
            continue;
        }
        if (std::regex_match(line, match, inst_pattern) && current_function) {
            AsmInstruction inst;
            inst.address = std::stoull(match[1].str(), nullptr, 16);
            inst.bytes = match[2].str();
            inst.opcode = match[3].str();
            inst.operands = trim(match[4].str());
            analyze_instruction(inst);
            current_function->instructions.push_back(inst);
            current_function->end_addr = inst.address;
        }
    }

    if (current_function) {
        functions.push_back(*current_function);
        delete current_function;
    }

    return functions;
}

std::pair<std::vector<Function>, std::string> disassemble_binary(const std::string& binary_path) {
    if (!fs::exists(binary_path)) {
        throw std::runtime_error("Binaire introuvable: " + binary_path);
    }

    std::string cmd = "objdump -d -M intel " + binary_path;
    std::string disasm_output;

    try {
        disasm_output = exec_command(cmd);
    } catch (const std::exception&) {
        throw std::runtime_error("Désassemblage échoué. Installez binutils: apt-get install binutils");
    }

    auto functions = parse_objdump_output(disasm_output);
    return {functions, disasm_output};
}

}  // namespace splitter
