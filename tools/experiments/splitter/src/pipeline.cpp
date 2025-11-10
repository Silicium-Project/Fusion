/*
 * Découpeur de binaires exécutables (.exe, ELF)
 * Désassemble le binaire → Analyse dépendances → Découpe en sous-programmes ASM
 * 
 * Compilation: g++ -std=c++17 -O2 binary_partitioner.cpp -o binary_partitioner
 * Usage: ./binary_partitioner <binary_file> [--output-dir <dir>]
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <set>
#include <map>
#include <unordered_map>
#include <memory>
#include <regex>
#include <cstdlib>
#include <cstdint>
#include <filesystem>
#include <algorithm>
#include <array>
#include <iomanip>
#include <optional>

#include "splitter/pipeline.hpp"

namespace splitter {

namespace fs = std::filesystem;

// ============================================================================
// STRUCTURES DE DONNÉES
// ============================================================================

struct AsmInstruction {
    uint64_t address = 0;
    std::string bytes;
    std::string opcode;
    std::string operands;
    std::set<std::string> reads;
    std::set<std::string> writes;
    bool is_jump = false;
    bool is_call = false;
    bool is_memory = false;
    std::optional<uint64_t> target_addr;
    
    std::string to_string() const {
        std::ostringstream oss;
        oss << "0x" << std::hex << address << ": " << opcode << " " << operands;
        return oss.str();
    }
};

struct Function {
    std::string name;
    uint64_t start_addr = 0;
    uint64_t end_addr = 0;
    std::vector<AsmInstruction> instructions;
    bool is_loop = false;
};

struct BinaryPartition {
    std::string id;
    std::vector<Function> functions;
    uint64_t start_addr = 0;
    uint64_t end_addr = 0;
    std::string asm_code;
    std::vector<uint8_t> raw_bytes;
    std::set<std::string> inputs;
    std::set<std::string> outputs;
    bool is_parallelizable = false;
    std::vector<std::string> dependencies;
    std::vector<std::string> parents;
    std::set<std::string> external_inputs;
    std::vector<std::string> unresolved_dependencies;
};

std::string json_escape(const std::string& input) {
    std::string result;
    result.reserve(input.size());
    for (char c : input) {
        switch (c) {
            case '\\': result += "\\\\"; break;
            case '"': result += "\\\""; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default: result += c; break;
        }
    }
    return result;
}

// ============================================================================
// UTILITAIRES
// ============================================================================

std::string exec_command(const std::string& cmd) {
    std::array<char, 128> buffer;
    std::string result;
    std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(cmd.c_str(), "r"), pclose);
    
    if (!pipe) {
        throw std::runtime_error("popen() échoué!");
    }
    
    while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
        result += buffer.data();
    }
    
    return result;
}

std::vector<std::string> split_string(const std::string& str, char delimiter) {
    std::vector<std::string> tokens;
    std::stringstream ss(str);
    std::string token;
    
    while (std::getline(ss, token, delimiter)) {
        tokens.push_back(token);
    }
    
    return tokens;
}

std::string trim(const std::string& str) {
    size_t first = str.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    size_t last = str.find_last_not_of(" \t\r\n");
    return str.substr(first, (last - first + 1));
}

// ============================================================================
// ANALYSE D'INSTRUCTIONS
// ============================================================================

void analyze_instruction(AsmInstruction& inst) {
    static const std::set<std::string> jump_opcodes = {
        "jmp", "je", "jne", "jg", "jge", "jl", "jle", 
        "ja", "jae", "jb", "jbe", "jz", "jnz", "js", 
        "jns", "jo", "jno", "jp", "jnp"
    };
    
    static const std::set<std::string> call_opcodes = {"call", "callq"};
    
    static const std::set<std::string> registers = {
        "rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rsp", "rbp",
        "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
        "eax", "ebx", "ecx", "edx", "esi", "edi", "esp", "ebp",
        "al", "ah", "bl", "bh", "cl", "ch", "dl", "dh", "sil", "dil",
        "xmm0", "xmm1", "xmm2", "xmm3", "xmm4", "xmm5", "xmm6", "xmm7"
    };
    
    // Détection de jumps
    if (jump_opcodes.count(inst.opcode)) {
        inst.is_jump = true;
        std::regex target_regex("0x([0-9a-f]+)");
        std::smatch match;
        if (std::regex_search(inst.operands, match, target_regex)) {
            inst.target_addr = std::stoull(match[1].str(), nullptr, 16);
        }
    }
    
    // Détection de calls
    if (call_opcodes.count(inst.opcode)) {
        inst.is_call = true;
        std::regex target_regex("0x([0-9a-f]+)");
        std::smatch match;
        if (std::regex_search(inst.operands, match, target_regex)) {
            inst.target_addr = std::stoull(match[1].str(), nullptr, 16);
        }
    }
    
    // Parser opérandes
    std::vector<std::string> ops;
    std::stringstream ss(inst.operands);
    std::string op;
    while (std::getline(ss, op, ',')) {
        ops.push_back(trim(op));
    }
    
    // Analyser chaque opérande
    for (const auto& op : ops) {
        // Accès mémoire
        if (op.find('[') != std::string::npos || op.find("PTR") != std::string::npos) {
            inst.is_memory = true;
            // Extraire registres
            for (const auto& reg : registers) {
                if (op.find(reg) != std::string::npos) {
                    inst.reads.insert(reg);
                }
            }
        } else {
            // Registre direct
            for (const auto& reg : registers) {
                if (op.find(reg) != std::string::npos) {
                    inst.reads.insert(reg);
                    break;
                }
            }
        }
    }
    
    // Déterminer writes
    if (!ops.empty() && inst.opcode != "cmp" && inst.opcode != "test" && inst.opcode != "push") {
        const std::string& dest = ops[0];
        
        if (dest.find('[') != std::string::npos || dest.find("PTR") != std::string::npos) {
            inst.is_memory = true;
        } else {
            for (const auto& reg : registers) {
                if (dest.find(reg) != std::string::npos) {
                    inst.writes.insert(reg);
                    break;
                }
            }
        }
    }
    
    // Opcodes spécifiques
    static const std::set<std::string> stack_ops = {"push", "pop", "call", "ret"};
    if (stack_ops.count(inst.opcode)) {
        inst.reads.insert("rsp");
        inst.writes.insert("rsp");
    }
    
    if (inst.opcode == "call") {
        // Call clobbers registres volatiles
        for (const auto& reg : {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}) {
            inst.writes.insert(reg);
        }
    }
}

// ============================================================================
// DÉSASSEMBLAGE DU BINAIRE
// ============================================================================

std::vector<Function> parse_objdump_output(const std::string& output) {
    std::vector<Function> functions;
    Function* current_function = nullptr;
    
    std::regex func_pattern("^([0-9a-f]+) <(.+)>:$");
    std::regex inst_pattern("^\\s*([0-9a-f]+):\\s+([0-9a-f ]+)\\s+(\\w+)\\s*(.*)$");
    
    std::istringstream stream(output);
    std::string line;
    
    while (std::getline(stream, line)) {
        std::smatch match;
        
        // Détecter début de fonction
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
        
        // Parser instruction
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
    } catch (const std::exception& e) {
        throw std::runtime_error("Désassemblage échoué. Installez binutils: apt-get install binutils");
    }
    
    auto functions = parse_objdump_output(disasm_output);
    return {functions, disasm_output};
}

// ============================================================================
// ANALYSE DE FONCTIONS
// ============================================================================

bool analyze_function_loops(Function& func) {
    for (const auto& inst : func.instructions) {
        if (inst.is_jump && inst.target_addr.has_value()) {
            if (inst.target_addr.value() <= inst.address) {
                func.is_loop = true;
                return true;
            }
        }
    }
    return false;
}

std::map<std::string, std::string> detect_loop_patterns(const Function& func) {
    std::map<std::string, std::string> result;
    
    if (!func.is_loop) {
        result["parallelizable"] = "false";
        return result;
    }
    
    // Analyser les accès mémoire
    bool has_memory_writes = false;
    
    for (const auto& inst : func.instructions) {
        if (!inst.writes.empty() && inst.is_memory) {
            has_memory_writes = true;
            break;
        }
    }
    
    if (!has_memory_writes) {
        result["parallelizable"] = "true";
        result["reason"] = "no memory writes";
    } else {
        result["parallelizable"] = "false";
        result["reason"] = "memory dependencies";
    }
    
    return result;
}

// ============================================================================
// EXTRACTION DE SEGMENTS BINAIRES
// ============================================================================

std::vector<uint8_t> extract_binary_segment(const std::string& binary_path, 
                                            uint64_t start_addr, 
                                            uint64_t end_addr) {
    std::vector<uint8_t> result;
    
    try {
        std::string cmd = "readelf -S " + binary_path;
        std::string output = exec_command(cmd);
        
        std::regex section_pattern("\\[\\s*\\d+\\]\\s+(\\.\\w+)\\s+\\w+\\s+([0-9a-f]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)");
        std::smatch match;
        
        uint64_t text_offset = 0;
        uint64_t text_vaddr = 0;
        
        std::istringstream stream(output);
        std::string line;
        
        while (std::getline(stream, line)) {
            if (std::regex_search(line, match, section_pattern) && 
                match[1].str().find(".text") != std::string::npos) {
                text_vaddr = std::stoull(match[2].str(), nullptr, 16);
                text_offset = std::stoull(match[3].str(), nullptr, 16);
                break;
            }
        }
        
        std::ifstream file(binary_path, std::ios::binary);
        if (!file) return result;
        
        uint64_t file_start = text_offset + (start_addr - text_vaddr);
        uint64_t file_end = text_offset + (end_addr - text_vaddr);
        
        file.seekg(file_start);
        result.resize(file_end - file_start);
        file.read(reinterpret_cast<char*>(result.data()), result.size());
        
    } catch (const std::exception& e) {
        std::cerr << "Avertissement: impossible d'extraire segment: " << e.what() << std::endl;
    }
    
    return result;
}

// ============================================================================
// PARTITIONNEMENT DU BINAIRE
// ============================================================================

std::string function_to_asm(const Function& func) {
    std::ostringstream oss;
    oss << "; Function: " << func.name << "\n";
    oss << "; Address: 0x" << std::hex << func.start_addr 
        << " - 0x" << func.end_addr << "\n\n";
    
    for (const auto& inst : func.instructions) {
        oss << "0x" << std::hex << inst.address << ": " 
            << std::left << std::setw(8) << inst.opcode << " " 
            << inst.operands << "\n";
    }
    
    return oss.str();
}

std::vector<BinaryPartition> partition_binary(std::vector<Function>& functions, 
                                              const std::string& binary_path) {
    std::vector<BinaryPartition> partitions;
    std::vector<std::vector<std::pair<std::optional<uint64_t>, std::string>>> call_refs;
    int partition_id = 0;
    
    for (auto& func : functions) {
        // Ignorer fonctions système/runtime
        if (func.name[0] == '_' || func.name.find("@plt") != std::string::npos) {
            continue;
        }
        
        analyze_function_loops(func);
        auto loop_info = detect_loop_patterns(func);
        
        BinaryPartition partition;
        partition.id = "func_" + std::to_string(partition_id) + "_" + func.name;
        partition.functions.push_back(func);
        partition.start_addr = func.start_addr;
        partition.end_addr = func.end_addr;
        partition.asm_code = function_to_asm(func);
        partition.raw_bytes = extract_binary_segment(binary_path, func.start_addr, func.end_addr);
        partition.is_parallelizable = (loop_info["parallelizable"] == "true");
        
        // Calculer inputs/outputs
        std::set<std::string> all_reads, all_writes;
        std::vector<std::pair<std::optional<uint64_t>, std::string>> function_calls;
        
        for (const auto& inst : func.instructions) {
            all_reads.insert(inst.reads.begin(), inst.reads.end());
            all_writes.insert(inst.writes.begin(), inst.writes.end());
            
            if (inst.is_call) {
                function_calls.push_back({inst.target_addr, inst.operands});
            }
        }
        
        std::set_difference(all_reads.begin(), all_reads.end(),
                          all_writes.begin(), all_writes.end(),
                          std::inserter(partition.inputs, partition.inputs.begin()));
        
        partition.outputs = all_writes;
        
        partitions.push_back(partition);
        call_refs.push_back(function_calls);
        partition_id++;
    }

    // Construire une table d'adresses → partitions
    std::unordered_map<uint64_t, size_t> addr_to_partition;
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        for (const auto& func : partitions[idx].functions) {
            addr_to_partition[func.start_addr] = idx;
        }
    }

    std::unordered_map<std::string, size_t> id_to_index;
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        id_to_index[partitions[idx].id] = idx;
    }

    std::vector<std::set<std::string>> parent_sets(partitions.size());

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        std::set<std::string> dependency_set;
        std::set<std::string> unresolved_set;

        for (const auto& call_info : call_refs[idx]) {
            if (call_info.first.has_value()) {
                uint64_t target = call_info.first.value();
                auto it = addr_to_partition.find(target);
                if (it != addr_to_partition.end()) {
                    const std::string& child_id = partitions[it->second].id;
                    if (child_id != partitions[idx].id) {
                        dependency_set.insert(child_id);
                        parent_sets[it->second].insert(partitions[idx].id);
                    }
                } else {
                    std::ostringstream oss;
                    if (!call_info.second.empty()) {
                        oss << call_info.second;
                    } else {
                        oss << "0x" << std::hex << target;
                    }
                    unresolved_set.insert(oss.str());
                }
            } else {
                if (!call_info.second.empty()) {
                    unresolved_set.insert(call_info.second);
                } else {
                    unresolved_set.insert("[indirect call]");
                }
            }
        }

        partitions[idx].dependencies.assign(dependency_set.begin(), dependency_set.end());
        partitions[idx].unresolved_dependencies.assign(unresolved_set.begin(), unresolved_set.end());
    }

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        partitions[idx].parents.assign(parent_sets[idx].begin(), parent_sets[idx].end());
    }

    // Calculer les inputs externes (non fournis par les parents)
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        std::set<std::string> provided;
        for (const auto& parent_id : partitions[idx].parents) {
            auto it = id_to_index.find(parent_id);
            if (it != id_to_index.end()) {
                const auto& parent_outputs = partitions[it->second].outputs;
                provided.insert(parent_outputs.begin(), parent_outputs.end());
            }
        }

        std::set<std::string> external_inputs;
        std::set_difference(partitions[idx].inputs.begin(), partitions[idx].inputs.end(),
                            provided.begin(), provided.end(),
                            std::inserter(external_inputs, external_inputs.begin()));
        partitions[idx].external_inputs = external_inputs;
    }
    
    return partitions;
}

// ============================================================================
// CRÉATION DE PARTITIONS STANDALONE
// ============================================================================

struct PartitionFiles {
    std::string asm_file;
    std::string bin_file;
    std::string wrapper_file;
};

PartitionFiles create_standalone_partition(const BinaryPartition& partition, 
                                          const std::string& output_dir) {
    fs::create_directories(output_dir);
    
    PartitionFiles files;
    files.asm_file = output_dir + "/" + partition.id + ".asm";
    files.bin_file = output_dir + "/" + partition.id + ".bin";
    files.wrapper_file = output_dir + "/" + partition.id + "_wrapper.c";
    
    // Sauvegarder ASM
    std::ofstream asm_out(files.asm_file);
    asm_out << partition.asm_code;
    asm_out.close();
    
    // Sauvegarder bytes bruts
    std::ofstream bin_out(files.bin_file, std::ios::binary);
    bin_out.write(reinterpret_cast<const char*>(partition.raw_bytes.data()), 
                  partition.raw_bytes.size());
    bin_out.close();
    
    // Créer wrapper C
    std::ofstream wrapper_out(files.wrapper_file);
    wrapper_out << "// Wrapper pour partition: " << partition.id << "\n"
                << "#include <stdio.h>\n"
                << "#include <stdint.h>\n\n"
                << "// Inputs: ";
    
    for (const auto& input : partition.inputs) {
        wrapper_out << input << " ";
    }
    
    wrapper_out << "\n// Inputs externes: ";
    
    for (const auto& input : partition.external_inputs) {
        wrapper_out << input << " ";
    }
    
    wrapper_out << "\n// Outputs: ";
    
    for (const auto& output : partition.outputs) {
        wrapper_out << output << " ";
    }

    if (!partition.parents.empty()) {
        wrapper_out << "\n// Parents: ";
        for (const auto& parent : partition.parents) {
            wrapper_out << parent << " ";
        }
    }
    
    if (!partition.dependencies.empty()) {
        wrapper_out << "\n// Dépendances internes: ";
        for (const auto& dep : partition.dependencies) {
            wrapper_out << dep << " ";
        }
    }
    
    if (!partition.unresolved_dependencies.empty()) {
        wrapper_out << "\n// Appels externes: ";
        for (const auto& dep : partition.unresolved_dependencies) {
            wrapper_out << dep << " ";
        }
    }
    
    wrapper_out << "\n\n"
                << "// Déclaration externe du code machine\n"
                << "extern void partition_code();\n\n"
                << "// Fonction wrapper\n"
                << "int main() {\n"
                << "    printf(\"Exécution partition: " << partition.id << "\\n\");\n"
                << "    \n"
                << "    // Appeler le code machine\n"
                << "    // Note: nécessite adaptation selon l'ABI\n"
                << "    // partition_code();\n"
                << "    \n"
                << "    printf(\"Partition terminée\\n\");\n"
                << "    return 0;\n"
                << "}\n";
    
    wrapper_out.close();
    
    return files;
}

// ============================================================================
// PROGRAMME PRINCIPAL
// ============================================================================

int run_cli(int argc, char* argv[]) {
    if (argc < 2) {
        std::cout << "Usage: " << argv[0] << " <binary_file> [--output-dir <dir>]\n\n"
                  << "Exemples:\n"
                  << "  " << argv[0] << " ./a.out\n"
                  << "  " << argv[0] << " program.exe --output-dir ./partitions\n\n"
                  << "Nécessite: objdump, readelf (binutils)\n";
        return 1;
    }
    
    std::string binary_path = argv[1];
    std::string output_dir = "./partitions";
    
    for (int i = 2; i < argc; i++) {
        if (std::string(argv[i]) == "--output-dir" && i + 1 < argc) {
            output_dir = argv[i + 1];
            i++;
        }
    }
    
    std::cout << "=== Désassemblage de " << binary_path << " ===\n\n";
    
    // 1. Désassembler le binaire
    std::vector<Function> functions;
    std::string disasm_full;
    
    try {
        auto result = disassemble_binary(binary_path);
        functions = result.first;
        disasm_full = result.second;
    } catch (const std::exception& e) {
        std::cerr << "Erreur: " << e.what() << std::endl;
        return 1;
    }
    
    std::cout << "Fonctions trouvées: " << functions.size() << "\n\n";
    
    // Afficher aperçu des fonctions
    std::cout << "=== Fonctions désassemblées ===\n\n";
    for (size_t i = 0; i < std::min(size_t(20), functions.size()); i++) {
        const auto& func = functions[i];
        uint64_t size = func.end_addr - func.start_addr;
        std::cout << "  " << std::left << std::setw(30) << func.name 
                  << " @ 0x" << std::hex << std::setw(10) << func.start_addr
                  << std::dec << " (" << std::setw(4) << func.instructions.size() 
                  << " insts, " << std::setw(5) << size << " bytes)\n";
    }
    
    if (functions.size() > 20) {
        std::cout << "  ... (" << (functions.size() - 20) << " autres fonctions)\n";
    }
    
    // Sauvegarder désassemblage complet
    std::ofstream full_asm("disassembly_full.asm");
    full_asm << disasm_full;
    full_asm.close();
    std::cout << "\nDésassemblage complet: disassembly_full.asm\n";
    
    std::cout << "\n=== Analyse des boucles ===\n\n";
    
    std::vector<Function*> loop_functions;
    for (auto& func : functions) {
        if (analyze_function_loops(func)) {
            loop_functions.push_back(&func);
        }
    }
    
    std::cout << "Fonctions avec boucles: " << loop_functions.size() << "\n\n";
    
    for (size_t i = 0; i < std::min(size_t(10), loop_functions.size()); i++) {
        const auto& func = *loop_functions[i];
        auto loop_info = detect_loop_patterns(func);
        std::string status = (loop_info["parallelizable"] == "true") ? 
            "PARALLÉLISABLE" : "SÉQUENTIELLE";
        
        std::cout << "  " << std::left << std::setw(30) << func.name 
                  << " - " << status << "\n";
        if (loop_info.count("reason")) {
            std::cout << "    Raison: " << loop_info["reason"] << "\n";
        }
    }
    
    std::cout << "\n=== Partitionnement du binaire ===\n\n";
    
    // 2. Partitionner
    auto partitions = partition_binary(functions, binary_path);
    
    std::cout << "Partitions créées: " << partitions.size() << "\n\n";
    
    // Créer répertoire de sortie
    fs::create_directories(output_dir);

    std::vector<PartitionFiles> generated_files;
    generated_files.reserve(partitions.size());
    
    // Sauvegarder chaque partition
    for (const auto& partition : partitions) {
        std::string status = partition.is_parallelizable ? "PARALLÈLE" : "SÉQUENTIEL";
        
        std::cout << "\nPartition: " << partition.id << " (" << status << ")\n";
        std::cout << "  Adresse: 0x" << std::hex << partition.start_addr 
                  << " - 0x" << partition.end_addr << std::dec << "\n";
        std::cout << "  Taille: " << partition.raw_bytes.size() << " bytes\n";
        
        std::cout << "  Inputs:  ";
        int count = 0;
        for (const auto& input : partition.inputs) {
            if (count++ >= 5) {
                std::cout << "...";
                break;
            }
            std::cout << input << " ";
        }
        std::cout << "\n";
        
        std::cout << "  Inputs externes: ";
        count = 0;
        for (const auto& input : partition.external_inputs) {
            if (count++ >= 5) {
                std::cout << "...";
                break;
            }
            std::cout << input << " ";
        }
        std::cout << "\n";
        
        std::cout << "  Outputs: ";
        count = 0;
        for (const auto& output : partition.outputs) {
            if (count++ >= 5) {
                std::cout << "...";
                break;
            }
            std::cout << output << " ";
        }
        std::cout << "\n";
        
        if (!partition.parents.empty()) {
            std::cout << "  Parents: ";
            count = 0;
            for (const auto& parent : partition.parents) {
                if (count++ >= 5) {
                    std::cout << "...";
                    break;
                }
                std::cout << parent << " ";
            }
            std::cout << "\n";
        }
        
        if (!partition.dependencies.empty()) {
            std::cout << "  Dépendances internes: ";
            count = 0;
            for (const auto& dep : partition.dependencies) {
                if (count++ >= 5) {
                    std::cout << "...";
                    break;
                }
                std::cout << dep << " ";
            }
            std::cout << "\n";
        }
        
        if (!partition.unresolved_dependencies.empty()) {
            std::cout << "  Appels externes: ";
            count = 0;
            for (const auto& dep : partition.unresolved_dependencies) {
                if (count++ >= 5) {
                    std::cout << "...";
                    break;
                }
                std::cout << dep << " ";
            }
            std::cout << "\n";
        }
        
        // Créer fichiers pour cette partition
        auto files = create_standalone_partition(partition, output_dir);
        generated_files.push_back(files);
        
        std::cout << "  Fichiers générés:\n";
        std::cout << "    - " << files.asm_file << "\n";
        std::cout << "    - " << files.bin_file << "\n";
        std::cout << "    - " << files.wrapper_file << "\n";
    }

    // Générer résumé JSON du graphe
    std::string summary_path = output_dir + "/summary.json";
    std::ofstream summary_out(summary_path);
    if (!summary_out) {
        std::cerr << "\nAvertissement: impossible d'écrire le résumé: " << summary_path << "\n";
    } else {
        auto to_json_array = [](const auto& container) {
            std::ostringstream oss;
            oss << "[";
            bool first = true;
            for (const auto& value : container) {
                if (!first) {
                    oss << ", ";
                }
                first = false;
                oss << "\"" << json_escape(value) << "\"";
            }
            oss << "]";
            return oss.str();
        };
        
        auto set_to_json = [&](const std::set<std::string>& container) {
            return to_json_array(container);
        };
        
        auto vector_to_json = [&](const std::vector<std::string>& container) {
            return to_json_array(container);
        };
        
        size_t parallelizable_count = 0;
        for (const auto& partition : partitions) {
            if (partition.is_parallelizable) {
                parallelizable_count++;
            }
        }
        
        summary_out << "{\n";
        summary_out << "  \"binary\": \"" << json_escape(binary_path) << "\",\n";
        summary_out << "  \"partitions_count\": " << partitions.size() << ",\n";
        summary_out << "  \"parallelizable_count\": " << parallelizable_count << ",\n";
        summary_out << "  \"partitions\": [\n";
        
        for (size_t idx = 0; idx < partitions.size(); ++idx) {
            const auto& partition = partitions[idx];
            summary_out << "    {\n";
            summary_out << "      \"id\": \"" << json_escape(partition.id) << "\",\n";
            summary_out << "      \"start\": \"0x" << std::hex << partition.start_addr << std::dec << "\",\n";
            summary_out << "      \"end\": \"0x" << std::hex << partition.end_addr << std::dec << "\",\n";
            summary_out << "      \"size\": " << partition.raw_bytes.size() << ",\n";
            summary_out << "      \"parallelizable\": " << (partition.is_parallelizable ? "true" : "false") << ",\n";
            summary_out << "      \"inputs\": " << set_to_json(partition.inputs) << ",\n";
            summary_out << "      \"external_inputs\": " << set_to_json(partition.external_inputs) << ",\n";
            summary_out << "      \"outputs\": " << set_to_json(partition.outputs) << ",\n";
            summary_out << "      \"parents\": " << vector_to_json(partition.parents) << ",\n";
            summary_out << "      \"dependencies\": " << vector_to_json(partition.dependencies) << ",\n";
            summary_out << "      \"unresolved_calls\": " << vector_to_json(partition.unresolved_dependencies) << ",\n";
            if (idx < generated_files.size()) {
                summary_out << "      \"asm\": \"" << json_escape(generated_files[idx].asm_file) << "\",\n";
                summary_out << "      \"bin\": \"" << json_escape(generated_files[idx].bin_file) << "\",\n";
                summary_out << "      \"wrapper\": \"" << json_escape(generated_files[idx].wrapper_file) << "\"\n";
            } else {
                summary_out << "      \"asm\": \"\",\n";
                summary_out << "      \"bin\": \"\",\n";
                summary_out << "      \"wrapper\": \"\"\n";
            }
            summary_out << "    }";
            if (idx + 1 < partitions.size()) {
                summary_out << ",";
            }
            summary_out << "\n";
        }
        
        summary_out << "  ]\n";
        summary_out << "}\n";
        summary_out.close();
        
        std::cout << "\nRésumé: " << summary_path << "\n";
    }
    
    std::cout << "\n=== Terminé ===\n";
    std::cout << "\nPartitions: " << output_dir << "/\n";
    
    return 0;
}

}  // namespace splitter
