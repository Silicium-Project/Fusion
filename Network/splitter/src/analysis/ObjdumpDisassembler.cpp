#include "analysis/ObjdumpDisassembler.hpp"

#include <cctype>
#include <filesystem>
#include <optional>
#include <regex>
#include <sstream>
#include <string>

#include "support/ShellCommand.hpp"
#include "support/StringUtil.hpp"

namespace splitter {

namespace fs = std::filesystem;

namespace {

const std::regex kFunctionPattern("^([0-9a-f]+) <(.+)>:$");
const std::regex kInstructionPattern("^\\s*([0-9a-f]+):\\s+([0-9a-f ]+)\\s+(\\w+)\\s*(.*)$");

std::size_t InstructionSizeFromBytes(const std::string& bytes) {
    std::size_t nybbles = 0;
    for (char ch : bytes)
        if (std::isxdigit(static_cast<unsigned char>(ch)))
            ++nybbles;
    if (!nybbles)
        return 0;
    return (nybbles + 1) / 2;
}

Function MakeFunction(const std::smatch& match) {
    Function func;
    func.SetStartAddr(std::stoull(match[1].str(), nullptr, 16));
    func.SetEndAddr(func.StartAddr());
    func.SetName(match[2].str());
    return func;
}

Instruction MakeInstruction(const std::smatch& match) {
    Instruction inst;
    inst.SetAddress(std::stoull(match[1].str(), nullptr, 16));
    inst.SetBytes(match[2].str());
    inst.SetOpcode(match[3].str());
    inst.SetOperands(Trim(match[4].str()));
    return inst;
}

void FlushCurrent(std::vector<Function>& functions, std::optional<Function>& current) {
    if (!current.has_value())
        return;
    functions.push_back(*current);
    current.reset();
}

bool StartNewFunction(const std::string& line, std::optional<Function>& current,
                      std::vector<Function>& functions) {
    std::smatch match;
    if (!std::regex_match(line, match, kFunctionPattern))
        return false;
    FlushCurrent(functions, current);
    current = MakeFunction(match);
    return true;
}

void AppendInstruction(const std::string& line, std::optional<Function>& current) {
    if (!current.has_value())
        return;
    std::smatch match;
    if (!std::regex_match(line, match, kInstructionPattern))
        return;
    Instruction inst = MakeInstruction(match);
    current->Instructions().push_back(inst);
    std::size_t inst_size = InstructionSizeFromBytes(inst.Bytes());
    current->SetEndAddr(inst.Address() + inst_size);
}

}  // namespace

ObjdumpDisassembler::ObjdumpDisassembler(std::string binary_path,
                                         SystemContext system)
    : binary_path_(std::move(binary_path)),
      system_(std::move(system)) {}

std::vector<Function> ObjdumpDisassembler::ParseOutput(const std::string& output) {
    std::vector<Function> functions;
    std::optional<Function> current;
    std::istringstream stream(output);
    std::string line;
    while (std::getline(stream, line)) {
        if (StartNewFunction(line, current, functions))
            continue;
        AppendInstruction(line, current);
    }
    FlushCurrent(functions, current);
    return functions;
}

std::pair<std::vector<Function>, std::string> ObjdumpDisassembler::Run() const {
    if (!system_.fs || !system_.fs->Exists(binary_path_))
        throw std::runtime_error("Binaire introuvable: " + binary_path_);

    std::string cmd = "objdump -d -M intel " + ShellQuote(binary_path_);
    std::string disasm_output;

    try {
        if (!system_.shell)
            throw std::runtime_error("Shell runner indisponible");
        disasm_output = system_.shell->Run(cmd);
    } catch (const std::exception&) {
        throw std::runtime_error("Désassemblage échoué. Installez binutils: apt-get install binutils");
    }

    auto functions = ParseOutput(disasm_output);
    return {functions, disasm_output};
}

}  // namespace splitter
