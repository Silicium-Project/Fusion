/*
 * Exécuteur de fragments binaires avec émulation des registres
 * Permet d'exécuter des fragments de manière sécurisée et de capturer les résultats
 * 
 * Compilation: g++ -std=c++17 -O2 fragment_executor.cpp -o fragment_executor
 */

#include <iostream>
#include <fstream>
#include <vector>
#include <map>
#include <string>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <memory>
#include <cstring>
#include <set>
#include <unordered_map>
#include <queue>
#include <algorithm>
#include <cctype>
#include <functional>
#include <stdexcept>

#ifdef __linux__
#include <sys/mman.h>
#include <unistd.h>
#endif

// ============================================================================
// UTILITAIRES JSON / GRAPHE
// ============================================================================

std::string trim(const std::string& str) {
    size_t first = str.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    size_t last = str.find_last_not_of(" \t\r\n");
    return str.substr(first, (last - first + 1));
}

size_t find_matching(const std::string& text, size_t start, char open_char, char close_char) {
    int depth = 0;
    for (size_t i = start; i < text.size(); ++i) {
        if (text[i] == open_char) {
            depth++;
        } else if (text[i] == close_char) {
            depth--;
            if (depth == 0) {
                return i;
            }
        }
    }
    return std::string::npos;
}

std::string extract_json_string(const std::string& object_text, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = object_text.find(pattern);
    if (pos == std::string::npos) return "";
    pos = object_text.find(':', pos);
    if (pos == std::string::npos) return "";
    pos = object_text.find('"', pos);
    if (pos == std::string::npos) return "";
    
    std::string value;
    bool escape = false;
    for (size_t i = pos + 1; i < object_text.size(); ++i) {
        char c = object_text[i];
        if (escape) {
            value += c;
            escape = false;
            continue;
        }
        if (c == '\\') {
            escape = true;
            continue;
        }
        if (c == '"') {
            break;
        }
        value += c;
    }
    return value;
}

std::vector<std::string> parse_json_string_array(const std::string& array_text) {
    std::vector<std::string> result;
    size_t pos = array_text.find('[');
    if (pos == std::string::npos) return result;
    pos++;
    
    while (pos < array_text.size()) {
        while (pos < array_text.size() && std::isspace(static_cast<unsigned char>(array_text[pos]))) {
            pos++;
        }
        if (pos >= array_text.size() || array_text[pos] == ']') {
            break;
        }
        if (array_text[pos] == '"') {
            pos++;
            std::string value;
            bool escape = false;
            for (; pos < array_text.size(); ++pos) {
                char c = array_text[pos];
                if (escape) {
                    value += c;
                    escape = false;
                    continue;
                }
                if (c == '\\') {
                    escape = true;
                    continue;
                }
                if (c == '"') {
                    pos++;
                    break;
                }
                value += c;
            }
            result.push_back(value);
            while (pos < array_text.size() && array_text[pos] != ',' && array_text[pos] != ']') {
                pos++;
            }
            if (pos < array_text.size() && array_text[pos] == ',') {
                pos++;
            }
        } else {
            while (pos < array_text.size() && array_text[pos] != ',' && array_text[pos] != ']') {
                pos++;
            }
            if (pos < array_text.size() && array_text[pos] == ',') {
                pos++;
            }
        }
    }
    return result;
}

std::vector<std::string> extract_json_array(const std::string& object_text, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = object_text.find(pattern);
    if (pos == std::string::npos) return {};
    pos = object_text.find('[', pos);
    if (pos == std::string::npos) return {};
    size_t end = find_matching(object_text, pos, '[', ']');
    if (end == std::string::npos) return {};
    std::string array_text = object_text.substr(pos, end - pos + 1);
    return parse_json_string_array(array_text);
}

bool extract_json_bool(const std::string& object_text, const std::string& key, bool default_value = false) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = object_text.find(pattern);
    if (pos == std::string::npos) return default_value;
    pos = object_text.find(':', pos);
    if (pos == std::string::npos) return default_value;
    pos++;
    while (pos < object_text.size() && std::isspace(static_cast<unsigned char>(object_text[pos]))) pos++;
    if (pos >= object_text.size()) return default_value;
    if (object_text.compare(pos, 4, "true") == 0) return true;
    if (object_text.compare(pos, 5, "false") == 0) return false;
    return default_value;
}

struct PartitionInfo {
    std::string id;
    std::string asm_path;
    std::string bin_path;
    std::string wrapper_path;
    std::set<std::string> inputs;
    std::set<std::string> external_inputs;
    std::set<std::string> outputs;
    std::vector<std::string> parents;
    std::vector<std::string> dependencies;
    std::vector<std::string> unresolved_calls;
    bool parallelizable = false;
};

std::vector<PartitionInfo> load_partition_summary(const std::string& summary_path) {
    std::ifstream file(summary_path);
    if (!file) {
        throw std::runtime_error("Impossible d'ouvrir le fichier de résumé: " + summary_path);
    }
    
    std::string content((std::istreambuf_iterator<char>(file)),
                        std::istreambuf_iterator<char>());
    
    std::vector<PartitionInfo> partitions;
    
    size_t partitions_pos = content.find("\"partitions\"");
    if (partitions_pos == std::string::npos) {
        throw std::runtime_error("Résumé invalide: champ \"partitions\" introuvable");
    }
    
    size_t array_start = content.find('[', partitions_pos);
    if (array_start == std::string::npos) {
        throw std::runtime_error("Résumé invalide: liste de partitions mal formée");
    }
    size_t array_end = find_matching(content, array_start, '[', ']');
    if (array_end == std::string::npos) {
        throw std::runtime_error("Résumé invalide: parenthèses non appariées");
    }
    
    size_t cursor = array_start;
    while (true) {
        size_t obj_start = content.find('{', cursor);
        if (obj_start == std::string::npos || obj_start > array_end) {
            break;
        }
        size_t obj_end = find_matching(content, obj_start, '{', '}');
        if (obj_end == std::string::npos) {
            throw std::runtime_error("Résumé invalide: accolades non appariées");
        }
        
        std::string object_text = content.substr(obj_start, obj_end - obj_start + 1);
        PartitionInfo info;
        info.id = extract_json_string(object_text, "id");
        info.asm_path = extract_json_string(object_text, "asm");
        info.bin_path = extract_json_string(object_text, "bin");
        info.wrapper_path = extract_json_string(object_text, "wrapper");
        info.parallelizable = extract_json_bool(object_text, "parallelizable", false);
        info.parents = extract_json_array(object_text, "parents");
        info.dependencies = extract_json_array(object_text, "dependencies");
        info.unresolved_calls = extract_json_array(object_text, "unresolved_calls");
        
        auto inputs_vec = extract_json_array(object_text, "inputs");
        info.inputs.insert(inputs_vec.begin(), inputs_vec.end());
        
        auto external_inputs_vec = extract_json_array(object_text, "external_inputs");
        info.external_inputs.insert(external_inputs_vec.begin(), external_inputs_vec.end());
        
        auto outputs_vec = extract_json_array(object_text, "outputs");
        info.outputs.insert(outputs_vec.begin(), outputs_vec.end());
        
        if (info.id.empty() || info.asm_path.empty()) {
            throw std::runtime_error("Résumé invalide: partition sans identifiant ou fichier ASM");
        }
        
        partitions.push_back(std::move(info));
        cursor = obj_end + 1;
    }
    
    if (partitions.empty()) {
        throw std::runtime_error("Résumé valide mais aucune partition trouvée");
    }
    
    return partitions;
}

std::vector<const PartitionInfo*> build_execution_plan(const std::vector<PartitionInfo>& partitions) {
    std::unordered_map<std::string, size_t> id_to_index;
    std::unordered_map<std::string, size_t> indegree;
    std::unordered_map<std::string, std::vector<std::string>> adjacency;
    
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        const auto& p = partitions[idx];
        id_to_index[p.id] = idx;
        indegree[p.id] = p.parents.size();
        adjacency[p.id];  // ensure key exists
    }
    
    for (const auto& partition : partitions) {
        for (const auto& dep : partition.dependencies) {
            auto it = id_to_index.find(dep);
            if (it == id_to_index.end()) {
                std::cerr << "⚠️  Avertissement: dépendance \"" << dep 
                          << "\" introuvable dans le résumé (appelée depuis " 
                          << partition.id << ")\n";
                continue;
            }
            adjacency[partition.id].push_back(dep);
        }
    }
    
    std::priority_queue<
        std::string,
        std::vector<std::string>,
        std::greater<std::string>
    > ready;
    for (const auto& [id, degree] : indegree) {
        if (degree == 0) {
            ready.push(id);
        }
    }
    
    std::vector<const PartitionInfo*> execution_order;
    execution_order.reserve(partitions.size());
    
    while (!ready.empty()) {
        std::string current = ready.top();
        ready.pop();
        
        auto idx_it = id_to_index.find(current);
        if (idx_it == id_to_index.end()) {
            continue;
        }
        
        execution_order.push_back(&partitions[idx_it->second]);
        
        for (const auto& child : adjacency[current]) {
            auto deg_it = indegree.find(child);
            if (deg_it == indegree.end()) {
                continue;
            }
            if (deg_it->second == 0) {
                continue;
            }
            deg_it->second--;
            if (deg_it->second == 0) {
                ready.push(child);
            }
        }
    }
    
    if (execution_order.size() != partitions.size()) {
        throw std::runtime_error("Cycle détecté dans le graphe de partitions: impossible de calculer un ordre d'exécution");
    }
    
    return execution_order;
}
// ============================================================================
// ÉMULATEUR DE REGISTRES x86-64
// ============================================================================

class RegisterEmulator {
public:
    // Registres généraux 64-bit
    std::map<std::string, uint64_t> regs64 = {
        {"rax", 0}, {"rbx", 0}, {"rcx", 0}, {"rdx", 0},
        {"rsi", 0}, {"rdi", 0}, {"rsp", 0}, {"rbp", 0},
        {"r8", 0}, {"r9", 0}, {"r10", 0}, {"r11", 0},
        {"r12", 0}, {"r13", 0}, {"r14", 0}, {"r15", 0}
    };
    
    // Flags
    bool ZF = false;  // Zero flag
    bool SF = false;  // Sign flag
    bool CF = false;  // Carry flag
    bool OF = false;  // Overflow flag
    
    // Mémoire simulée (1MB)
    std::vector<uint8_t> memory;
    uint64_t stack_base;
    
    RegisterEmulator() {
        memory.resize(1024 * 1024, 0);  // 1MB
        stack_base = memory.size() - 0x10000;  // Stack à la fin
        regs64["rsp"] = stack_base;
        regs64["rbp"] = stack_base;
    }
    
    uint64_t get(const std::string& reg) const {
        auto it = regs64.find(reg);
        if (it != regs64.end()) return it->second;
        
        // Registres 32-bit (eax, ebx, etc)
        if (reg.size() == 3 && reg[0] == 'e') {
            std::string r64 = "r" + reg.substr(1);
            auto it64 = regs64.find(r64);
            if (it64 != regs64.end()) {
                return it64->second & 0xFFFFFFFF;
            }
        }
        
        return 0;
    }
    
    void set(const std::string& reg, uint64_t value) {
        auto it = regs64.find(reg);
        if (it != regs64.end()) {
            it->second = value;
            return;
        }
        
        // Registres 32-bit
        if (reg.size() == 3 && reg[0] == 'e') {
            std::string r64 = "r" + reg.substr(1);
            auto it64 = regs64.find(r64);
            if (it64 != regs64.end()) {
                it64->second = (it64->second & 0xFFFFFFFF00000000ULL) | (value & 0xFFFFFFFF);
            }
        }
    }
    
    void write_memory(uint64_t addr, const void* data, size_t size) {
        if (addr + size <= memory.size()) {
            std::memcpy(&memory[addr], data, size);
        }
    }
    
    void read_memory(uint64_t addr, void* data, size_t size) const {
        if (addr + size <= memory.size()) {
            std::memcpy(data, &memory[addr], size);
        }
    }
    
    void print_state() const {
        std::cout << "\n=== État des registres ===\n";
        for (const auto& [reg, val] : regs64) {
            std::cout << std::setw(4) << reg << " = 0x" 
                      << std::hex << std::setw(16) << std::setfill('0') 
                      << val << std::dec << std::setfill(' ') 
                      << " (" << val << ")\n";
        }
        std::cout << "\nFlags: ZF=" << ZF << " SF=" << SF 
                  << " CF=" << CF << " OF=" << OF << "\n";
    }
};

// ============================================================================
// RÉSULTAT D'EXÉCUTION
// ============================================================================

struct ExecutionResult {
    bool success = false;
    std::string error_message;
    
    // État des registres avant/après
    std::map<std::string, uint64_t> initial_regs;
    std::map<std::string, uint64_t> final_regs;
    
    // Registres modifiés
    std::map<std::string, std::pair<uint64_t, uint64_t>> changed_regs;  // old -> new
    
    // Statistiques
    size_t instructions_executed = 0;
    size_t memory_accesses = 0;
    
    void print() const {
        if (!success) {
            std::cout << "❌ Exécution échouée: " << error_message << "\n";
            return;
        }
        
        std::cout << "✅ Exécution réussie\n";
        std::cout << "Instructions exécutées: " << instructions_executed << "\n";
        std::cout << "Accès mémoire: " << memory_accesses << "\n";
        
        if (!changed_regs.empty()) {
            std::cout << "\n=== Registres modifiés ===\n";
            for (const auto& [reg, vals] : changed_regs) {
                std::cout << std::setw(4) << reg << ": "
                          << "0x" << std::hex << std::setw(16) << std::setfill('0') << vals.first
                          << " → 0x" << std::setw(16) << vals.second << std::dec << std::setfill(' ') << "\n";
            }
        }
    }
};

// ============================================================================
// EXÉCUTEUR DE FRAGMENT (MODE JIT SIMPLIFIÉ)
// ============================================================================

class FragmentExecutor {
private:
    RegisterEmulator emulator;
    bool use_native_execution;
    
public:
    FragmentExecutor(bool native = false) : use_native_execution(native) {}
    
    // Préparer les registres d'entrée
    void set_input(const std::string& reg, uint64_t value) {
        emulator.set(reg, value);
    }
    
    void set_inputs(const std::map<std::string, uint64_t>& inputs) {
        for (const auto& [reg, val] : inputs) {
            emulator.set(reg, val);
        }
    }

    uint64_t get_register(const std::string& reg) const {
        return emulator.get(reg);
    }
    
    // Exécution SÉCURISÉE via émulation (recommandé)
    ExecutionResult execute_safe(const std::string& asm_file) {
        ExecutionResult result;
        
        // Lire le fichier ASM
        std::ifstream file(asm_file);
        if (!file) {
            result.error_message = "Impossible d'ouvrir " + asm_file;
            return result;
        }
        
        // Sauvegarder état initial
        result.initial_regs = emulator.regs64;
        
        std::cout << "\n🔒 Exécution SÉCURISÉE (émulation)\n";
        std::cout << "Fichier: " << asm_file << "\n";
        
        // Parser et émuler chaque instruction
        std::string line;
        while (std::getline(file, line)) {
            // Ignorer commentaires et lignes vides
            if (line.empty() || line[0] == ';' || line[0] == '#') continue;
            
            // Simuler l'exécution
            if (!emulate_instruction(line, result)) {
                result.error_message = "Erreur lors de l'émulation: " + line;
                return result;
            }
            
            result.instructions_executed++;
        }
        
        // Sauvegarder état final
        result.final_regs = emulator.regs64;
        
        // Calculer les différences
        for (const auto& [reg, final_val] : result.final_regs) {
            uint64_t initial_val = result.initial_regs[reg];
            if (initial_val != final_val) {
                result.changed_regs[reg] = {initial_val, final_val};
            }
        }
        
        result.success = true;
        return result;
    }
    
    // Exécution NATIVE via JIT (DANGEREUX - à utiliser avec précaution)
    ExecutionResult execute_native(const std::vector<uint8_t>& binary_code) {
        ExecutionResult result;
        
        std::cout << "\n⚠️  AVERTISSEMENT: Exécution NATIVE (JIT)\n";
        std::cout << "Ceci est potentiellement dangereux!\n";
        
#ifdef __linux__
        // Allouer mémoire exécutable
        #include <sys/mman.h>
        
        void* exec_mem = mmap(nullptr, binary_code.size(), 
                             PROT_READ | PROT_WRITE | PROT_EXEC,
                             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        
        if (exec_mem == MAP_FAILED) {
            result.error_message = "Impossible d'allouer mémoire exécutable";
            return result;
        }
        
        // Copier le code
        std::memcpy(exec_mem, binary_code.data(), binary_code.size());
        
        // Sauvegarder état initial
        result.initial_regs = emulator.regs64;
        
        // Créer un wrapper pour capturer les registres
        // ATTENTION: Ceci est très expérimental et peut crasher!
        
        try {
            // Exécuter le code (TRÈS DANGEREUX)
            void (*func)() = (void(*)())exec_mem;
            func();
            
            result.success = true;
        } catch (...) {
            result.error_message = "Crash pendant l'exécution native";
        }
        
        // Libérer la mémoire
        munmap(exec_mem, binary_code.size());
#else
        result.error_message = "Exécution native non supportée sur cette plateforme";
#endif
        
        return result;
    }
    
    void print_register_state() const {
        emulator.print_state();
    }
    
private:
    bool emulate_instruction(const std::string& line, ExecutionResult& result) {
        // Parser l'instruction (format: address: opcode operands)
        size_t colon_pos = line.find(':');
        if (colon_pos == std::string::npos) return true;
        
        std::string instruction = line.substr(colon_pos + 1);
        
        // Séparer opcode et opérandes
        std::istringstream iss(instruction);
        std::string opcode;
        iss >> opcode;
        
        // Émulation simplifiée des instructions les plus courantes
        if (opcode == "mov" || opcode == "movq" || opcode == "movl") {
            return emulate_mov(iss, result);
        } else if (opcode == "add" || opcode == "addq" || opcode == "addl") {
            return emulate_add(iss, result);
        } else if (opcode == "sub" || opcode == "subq" || opcode == "subl") {
            return emulate_sub(iss, result);
        } else if (opcode == "xor" || opcode == "xorq" || opcode == "xorl") {
            return emulate_xor(iss, result);
        } else if (opcode == "inc" || opcode == "incq" || opcode == "incl") {
            return emulate_inc(iss, result);
        } else if (opcode == "dec" || opcode == "decq" || opcode == "decl") {
            return emulate_dec(iss, result);
        } else if (opcode == "push" || opcode == "pushq") {
            return emulate_push(iss, result);
        } else if (opcode == "pop" || opcode == "popq") {
            return emulate_pop(iss, result);
        } else if (opcode == "ret" || opcode == "retq") {
            return true; // Fin de fonction
        } else if (opcode == "nop") {
            return true; // No operation
        }
        
        // Instruction non supportée - continuer quand même
        return true;
    }
    
    bool emulate_mov(std::istringstream& iss, ExecutionResult& result) {
        std::string dest, src;
        std::getline(iss, dest, ',');
        std::getline(iss, src);
        
        dest = trim(dest);
        src = trim(src);
        
        if (dest.empty() || src.empty()) return false;
        
        // Vérifier si c'est un accès mémoire
        if (dest[0] == '[') {
            result.memory_accesses++;
            return true;  // Accès mémoire - ignorer pour l'instant
        }
        
        // MOV registre <- valeur immédiate
        if (src[0] == '$' || (src[0] >= '0' && src[0] <= '9')) {
            uint64_t value = parse_immediate(src);
            emulator.set(dest, value);
        }
        // MOV registre <- registre
        else {
            uint64_t value = emulator.get(src);
            emulator.set(dest, value);
        }
        
        return true;
    }
    
    bool emulate_add(std::istringstream& iss, ExecutionResult& result) {
        std::string dest, src;
        std::getline(iss, dest, ',');
        std::getline(iss, src);
        
        dest = trim(dest);
        src = trim(src);
        
        if (dest[0] == '[') {
            result.memory_accesses++;
            return true;
        }
        
        uint64_t dest_val = emulator.get(dest);
        uint64_t src_val = (src[0] == '$' || (src[0] >= '0' && src[0] <= '9')) 
                          ? parse_immediate(src) 
                          : emulator.get(src);
        
        uint64_t result_val = dest_val + src_val;
        emulator.set(dest, result_val);
        
        // Mise à jour des flags
        emulator.ZF = (result_val == 0);
        emulator.SF = (result_val & (1ULL << 63)) != 0;
        
        return true;
    }
    
    bool emulate_sub(std::istringstream& iss, ExecutionResult& result) {
        std::string dest, src;
        std::getline(iss, dest, ',');
        std::getline(iss, src);
        
        dest = trim(dest);
        src = trim(src);
        
        if (dest[0] == '[') {
            result.memory_accesses++;
            return true;
        }
        
        uint64_t dest_val = emulator.get(dest);
        uint64_t src_val = (src[0] == '$' || (src[0] >= '0' && src[0] <= '9')) 
                          ? parse_immediate(src) 
                          : emulator.get(src);
        
        uint64_t result_val = dest_val - src_val;
        emulator.set(dest, result_val);
        
        emulator.ZF = (result_val == 0);
        emulator.SF = (result_val & (1ULL << 63)) != 0;
        
        return true;
    }
    
    bool emulate_xor(std::istringstream& iss, ExecutionResult& result) {
        std::string dest, src;
        std::getline(iss, dest, ',');
        std::getline(iss, src);
        
        dest = trim(dest);
        src = trim(src);
        
        uint64_t dest_val = emulator.get(dest);
        uint64_t src_val = emulator.get(src);
        
        uint64_t result_val = dest_val ^ src_val;
        emulator.set(dest, result_val);
        
        emulator.ZF = (result_val == 0);
        emulator.SF = (result_val & (1ULL << 63)) != 0;
        emulator.CF = false;
        emulator.OF = false;
        
        return true;
    }
    
    bool emulate_inc(std::istringstream& iss, ExecutionResult& result) {
        std::string dest;
        iss >> dest;
        dest = trim(dest);
        
        uint64_t val = emulator.get(dest);
        emulator.set(dest, val + 1);
        
        return true;
    }
    
    bool emulate_dec(std::istringstream& iss, ExecutionResult& result) {
        std::string dest;
        iss >> dest;
        dest = trim(dest);
        
        uint64_t val = emulator.get(dest);
        emulator.set(dest, val - 1);
        
        return true;
    }
    
    bool emulate_push(std::istringstream& iss, ExecutionResult& result) {
        std::string src;
        iss >> src;
        src = trim(src);
        
        uint64_t rsp = emulator.get("rsp");
        rsp -= 8;
        emulator.set("rsp", rsp);
        
        uint64_t value = emulator.get(src);
        emulator.write_memory(rsp, &value, 8);
        result.memory_accesses++;
        
        return true;
    }
    
    bool emulate_pop(std::istringstream& iss, ExecutionResult& result) {
        std::string dest;
        iss >> dest;
        dest = trim(dest);
        
        uint64_t rsp = emulator.get("rsp");
        uint64_t value;
        emulator.read_memory(rsp, &value, 8);
        
        emulator.set(dest, value);
        emulator.set("rsp", rsp + 8);
        result.memory_accesses++;
        
        return true;
    }
    
    uint64_t parse_immediate(const std::string& str) const {
        std::string s = str;
        if (s[0] == '$') s = s.substr(1);
        
        if (s.substr(0, 2) == "0x") {
            return std::stoull(s, nullptr, 16);
        }
        return std::stoull(s);
    }
    
    std::string trim(const std::string& str) const {
        size_t first = str.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) return "";
        size_t last = str.find_last_not_of(" \t\r\n");
        return str.substr(first, (last - first + 1));
    }
};

// ============================================================================
// PROGRAMME PRINCIPAL
// ============================================================================

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cout << "Usage: " << argv[0] << " <asm_file> [<asm_file> ...] [--input reg=value ...] [--native]\n"
                  << "   ou : " << argv[0] << " --summary partitions/summary.json [--input reg=value ...] [--native]\n\n"
                  << "Exemples:\n"
                  << "  " << argv[0] << " partition.asm\n"
                  << "  " << argv[0] << " func_0.asm func_1.asm --input rax=42 rbx=100\n"
                  << "  " << argv[0] << " --summary partitions/summary.json --input rdi=0x1000\n\n"
                  << "Options:\n"
                  << "  --summary fichier : Charger le graphe d'exécution généré par splitter\n"
                  << "  --input reg=value : Définir une valeur d'entrée pour un registre\n"
                  << "  --native          : Exécution native (DANGEREUX!)\n";
        return 1;
    }
    
    std::vector<std::string> asm_files;
    std::map<std::string, uint64_t> inputs;
    bool native_mode = false;
    std::string summary_file;
    
    // Parser les arguments
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        
        if (arg == "--native") {
            native_mode = true;
        } else if (arg == "--summary") {
            if (i + 1 >= argc) {
                std::cerr << "❌ Option --summary requiert un fichier (summary.json)\n";
                return 1;
            }
            summary_file = argv[++i];
        } else if (arg == "--input") {
            if (i + 1 >= argc) {
                std::cerr << "❌ Option --input requiert un argument de la forme reg=val\n";
                return 1;
            }
            i++;
            std::string input_arg = argv[i];
            size_t eq_pos = input_arg.find('=');
            if (eq_pos != std::string::npos) {
                std::string reg = input_arg.substr(0, eq_pos);
                std::string val_str = input_arg.substr(eq_pos + 1);
                
                uint64_t value;
                if (val_str.size() > 2 && val_str.substr(0, 2) == "0x") {
                    value = std::stoull(val_str, nullptr, 16);
                } else {
                    value = std::stoull(val_str);
                }
                
                inputs[reg] = value;
            } else {
                std::cerr << "❌ Argument d'entrée invalide: " << input_arg << "\n";
                return 1;
            }
        } else {
            asm_files.push_back(arg);
        }
    }
    
    if (!summary_file.empty() && !asm_files.empty()) {
        std::cerr << "❌ Merci de choisir soit des fichiers ASM explicites, soit un fichier --summary, mais pas les deux.\n";
        return 1;
    }
    
    if (summary_file.empty() && asm_files.empty()) {
        std::cout << "❌ Aucun fichier ASM ni fichier résumé fourni.\n";
        return 1;
    }
    
    std::vector<PartitionInfo> partition_infos;
    std::vector<const PartitionInfo*> ordered_partitions;
    
    if (!summary_file.empty()) {
        try {
            partition_infos = load_partition_summary(summary_file);
            ordered_partitions = build_execution_plan(partition_infos);
        } catch (const std::exception& e) {
            std::cerr << "❌ Erreur lors du chargement du graphe: " << e.what() << "\n";
            return 1;
        }
    }
    
    std::cout << "╔════════════════════════════════════════════════════════════╗\n";
    std::cout << "║         EXÉCUTEUR DE FRAGMENTS BINAIRES                   ║\n";
    std::cout << "╚════════════════════════════════════════════════════════════╝\n";
    
    // Créer l'exécuteur
    FragmentExecutor executor(native_mode);
    
    // Définir les entrées
    if (!inputs.empty()) {
        std::cout << "\n📥 Valeurs d'entrée:\n";
        for (const auto& [reg, val] : inputs) {
            std::cout << "  " << reg << " = 0x" << std::hex << val << std::dec 
                      << " (" << val << ")\n";
            executor.set_input(reg, val);
        }
    }
    
    // Afficher état initial
    std::cout << "\n📊 État initial des registres:\n";
    executor.print_register_state();
    
    struct ExecutionEntry {
        std::string name;
        std::string asm_path;
        const PartitionInfo* meta = nullptr;
    };
    
    std::vector<ExecutionEntry> execution_plan;
    std::set<std::string> consumed_external_inputs;
    std::set<std::string> expected_external_inputs;
    
    if (!ordered_partitions.empty()) {
        execution_plan.reserve(ordered_partitions.size());
        for (const auto* meta : ordered_partitions) {
            ExecutionEntry entry;
            entry.name = meta->id;
            entry.asm_path = meta->asm_path;
            entry.meta = meta;
            execution_plan.push_back(entry);
            expected_external_inputs.insert(meta->external_inputs.begin(), meta->external_inputs.end());
        }
        
        std::cout << "\n📦 Graphe chargé: " << ordered_partitions.size() << " partitions\n";
        std::cout << "   Fichier: " << summary_file << "\n";
        if (!execution_plan.empty()) {
            std::cout << "   Ordre d'exécution: ";
            for (size_t i = 0; i < execution_plan.size(); ++i) {
                if (i > 0) std::cout << " -> ";
                std::cout << execution_plan[i].name;
            }
            std::cout << "\n";
        }
    } else {
        execution_plan.reserve(asm_files.size());
        for (const auto& file : asm_files) {
            ExecutionEntry entry;
            entry.name = file;
            entry.asm_path = file;
            entry.meta = nullptr;
            execution_plan.push_back(entry);
        }
    }
    
    // Exécuter les fragments en chaîne
    ExecutionResult last_result;
    bool all_success = true;
    
    for (size_t idx = 0; idx < execution_plan.size(); ++idx) {
        const auto& entry = execution_plan[idx];
        
        std::cout << "\n══════════════════════════════════════════════════════════════\n";
        std::cout << "▶️  Fragment " << idx << " : " << entry.name << "\n";
        std::cout << "══════════════════════════════════════════════════════════════\n";
        
        if (entry.meta) {
            if (!entry.meta->parents.empty()) {
                std::cout << "  Parents: ";
                for (size_t p = 0; p < entry.meta->parents.size(); ++p) {
                    if (p > 0) std::cout << ", ";
                    std::cout << entry.meta->parents[p];
                }
                std::cout << "\n";
            }
            
            if (!entry.meta->dependencies.empty()) {
                std::cout << "  Dépendances internes: ";
                for (size_t d = 0; d < entry.meta->dependencies.size(); ++d) {
                    if (d > 0) std::cout << ", ";
                    std::cout << entry.meta->dependencies[d];
                }
                std::cout << "\n";
            }
            
            if (!entry.meta->unresolved_calls.empty()) {
                std::cout << "  Appels externes: ";
                for (size_t d = 0; d < entry.meta->unresolved_calls.size(); ++d) {
                    if (d > 0) std::cout << ", ";
                    std::cout << entry.meta->unresolved_calls[d];
                }
                std::cout << "\n";
            }
            
            if (!entry.meta->external_inputs.empty()) {
                std::cout << "  Préparation inputs externes:\n";
                for (const auto& reg : entry.meta->external_inputs) {
                    auto it = inputs.find(reg);
                    if (it != inputs.end()) {
                        executor.set_input(reg, it->second);
                        consumed_external_inputs.insert(reg);
                        std::cout << "    - " << reg << " = 0x" << std::hex << it->second 
                                  << std::dec << " (" << it->second << ") via --input\n";
                    } else {
                        uint64_t current_value = executor.get_register(reg);
                        std::cout << "    - " << reg << " (valeur actuelle) = 0x" << std::hex 
                                  << current_value << std::dec << " (" << current_value << ")\n";
                    }
                }
            }
            
            if (!entry.meta->asm_path.empty() && entry.asm_path != entry.meta->asm_path) {
                std::cout << "  Fichier ASM: " << entry.meta->asm_path << "\n";
            }
        }
        
        if (native_mode) {
            std::string bin_file;
            if (entry.meta && !entry.meta->bin_path.empty()) {
                bin_file = entry.meta->bin_path;
            } else {
                bin_file = entry.asm_path;
                size_t dot_pos = bin_file.rfind('.');
                if (dot_pos != std::string::npos) {
                    bin_file = bin_file.substr(0, dot_pos) + ".bin";
                }
            }
            
            std::ifstream file(bin_file, std::ios::binary);
            if (!file) {
                std::cerr << "❌ Impossible d'ouvrir " << bin_file << "\n";
                return 1;
            }
            
            std::vector<uint8_t> binary_code((std::istreambuf_iterator<char>(file)),
                                             std::istreambuf_iterator<char>());
            
            last_result = executor.execute_native(binary_code);
        } else {
            last_result = executor.execute_safe(entry.asm_path);
        }
        
        std::cout << "\n╔════════════════════════════════════════════════════════════╗\n";
        std::cout << "║                    RÉSULTATS                               ║\n";
        std::cout << "╚════════════════════════════════════════════════════════════╝\n\n";
        last_result.print();
        
        if (!last_result.success) {
            all_success = false;
            std::cout << "\n❌ Arrêt: échec de l'exécution pour " << entry.asm_path << "\n";
            break;
        }
    }
    
    if (all_success) {
        std::cout << "\n📊 État final des registres:\n";
        executor.print_register_state();
    }
    
    if (!summary_file.empty() && !inputs.empty()) {
        std::vector<std::string> unused;
        for (const auto& [reg, value] : inputs) {
            if (!expected_external_inputs.count(reg)) {
                continue;
            }
            if (!consumed_external_inputs.count(reg)) {
                unused.push_back(reg);
            }
        }
        if (!unused.empty()) {
            std::cout << "\n⚠️  Valeurs --input non consommées (aucune partition ne les demande directement): ";
            for (size_t i = 0; i < unused.size(); ++i) {
                if (i > 0) std::cout << ", ";
                std::cout << unused[i];
            }
            std::cout << "\n";
        }
    }
    
    return all_success ? 0 : 1;
}
