#include "runtime/NativeRunner.hpp"

#include "support/Logging.hpp"
#include "partition/PartitionRegistry.hpp"
#include "partition/PartitionSummary.hpp"
#include "support/Utils.hpp"

#include <fstream>
#include <iterator>
#include <sstream>
#include <vector>
#ifdef __linux__
#include <dlfcn.h>
#endif

namespace fragment {

namespace {

PartitionRegistry& registry() {
    return global_partition_registry();
}

std::vector<uint8_t> read_binary_file(const std::string& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        log::warning("Impossible d'ouvrir " + path
                     + " pour initialiser les dÃ©pendances natives.");
        return {};
    }
    return std::vector<uint8_t>(std::istreambuf_iterator<char>(file), {});
}

std::string binary_path_from_info(const PartitionInfo& info) {
    if (!info.bin_path.empty())
        return info.bin_path;
    std::string path = info.asm_path;
    size_t dot_pos = path.rfind('.');
    if (dot_pos != std::string::npos)
        path = path.substr(0, dot_pos);
    return path + ".bin";
}

bool is_runtime_partition(const PartitionInfo& meta) {
    const std::string& id = meta.id;
    return id.find("_init") != std::string::npos
           || id.find("_fini") != std::string::npos
           || id.find("tm_clones") != std::string::npos
           || id.find("frame_dummy") != std::string::npos
           || id.find("__do_global_dtors_aux") != std::string::npos
           || id.find("_dl_relocate_static_pie") != std::string::npos;
}

struct UnresolvedHook {
    uint64_t address = 0;
    std::string symbol;
};

std::optional<UnresolvedHook> parse_unresolved_descriptor(const std::string& desc) {
    size_t lt = desc.find('<');
    size_t gt = desc.find('>', lt == std::string::npos ? 0 : lt + 1);
    if (lt == std::string::npos || gt == std::string::npos)
        return std::nullopt;
    std::string addr_text = fragment::trim(desc.substr(0, lt));
    if (addr_text.empty())
        return std::nullopt;
    uint64_t addr = 0;
    try {
        addr = std::stoull(addr_text, nullptr, 16);
    } catch (...) {
        return std::nullopt;
    }
    std::string symbol = desc.substr(lt + 1, gt - lt - 1);
    auto at_pos = symbol.find('@');
    if (at_pos != std::string::npos)
        symbol = symbol.substr(0, at_pos);
    return UnresolvedHook{addr, symbol};
}

struct HookReport {
    std::vector<std::string> missing_symbols;
    std::vector<std::string> unsafe_calls;

    bool ok() const {
        return missing_symbols.empty() && unsafe_calls.empty();
    }
};

std::vector<uint8_t> make_jmp_stub(uint64_t target_addr) {
    std::vector<uint8_t> stub;
    stub.reserve(12);
    stub.push_back(0x48);
    stub.push_back(0xB8);
    for (size_t idx = 0; idx < 8; ++idx)
        stub.push_back(static_cast<uint8_t>((target_addr >> (idx * 8)) & 0xFF));
    stub.push_back(0xFF);
    stub.push_back(0xE0);
    return stub;
}

std::vector<uint8_t> make_ret_stub() {
    return {0xC3};
}

std::optional<uint64_t> resolve_symbol_addr(const std::string& symbol) {
#ifdef __linux__
    if (symbol.empty())
        return std::nullopt;
    void* target = dlsym(RTLD_DEFAULT, symbol.c_str());
    if (!target)
        return std::nullopt;
    return reinterpret_cast<uint64_t>(target);
#else
    (void)symbol;
    return std::nullopt;
#endif
}

void preload_dependency_code(const PartitionInfo& meta, FragmentExecutor& executor) {
    auto parts = registry().partitions();
    if (!parts.has_value())
        return;

    std::function<void(const PartitionInfo&)> loader = [&](const PartitionInfo& part) {
        for (const auto& dep_id : part.dependencies) {
            if (!registry().mark_preloaded(dep_id))
                continue;
            auto dep = registry().find(dep_id);
            if (!dep) {
                log::warning("Partition dÃ©pendante inconnue: " + dep_id);
                continue;
            }
            const PartitionInfo& dep_meta = dep->get();
            if (!dep_meta.start_address.has_value()) {
                log::warning("Adresse de dÃ©part manquante pour la partition dÃ©pendante: " + dep_id);
                continue;
            }
            const std::string bin_path = binary_path_from_info(dep_meta);
            auto bytes = read_binary_file(bin_path);
            if (bytes.empty())
                continue;
            executor.preload_native_chunk(*dep_meta.start_address, bytes);
            loader(dep_meta);
        }
    };

    loader(meta);
}

std::optional<uint64_t> parse_addr_token(const std::string& text) {
    std::string token = text;
    auto cut = token.find_first_of(" <\t");
    if (cut != std::string::npos)
        token = token.substr(0, cut);
    if (token.empty())
        return std::nullopt;
    try {
        return std::stoull(token, nullptr, 16);
    } catch (...) {
        return std::nullopt;
    }
}

HookReport install_unresolved_hooks(const PartitionInfo& meta,
                                    FragmentExecutor& executor,
                                    bool allow_stub) {
    HookReport report;
#ifdef __linux__
    for (const auto& call : meta.unresolved_calls) {
        auto info = parse_unresolved_descriptor(call);
        if (!info) {
            report.unsafe_calls.push_back(call);
            continue;
        }

        if (info->symbol.empty()) {
            report.unsafe_calls.push_back(call);
            if (allow_stub)
                executor.preload_native_chunk(info->address, make_ret_stub());
            continue;
        }
        auto resolved = resolve_symbol_addr(info->symbol);
        if (!resolved) {
            report.missing_symbols.push_back(info->symbol);
            if (!allow_stub)
                continue;
            log::warning("dlsym a échoué pour " + info->symbol + ", fallback ret");
            executor.preload_native_chunk(info->address, make_ret_stub());
            continue;
        }
        executor.preload_native_chunk(info->address, make_jmp_stub(*resolved));
    }

    for (const auto& call : meta.external_calls) {
        auto addr_opt = parse_addr_token(call);
        if (!addr_opt) {
            report.unsafe_calls.push_back(call);
            continue;
        }
        uint64_t addr = *addr_opt;

        // Tenter de récupérer le symbole éventuel entre <...>
        std::string symbol;
        auto lt = call.find('<');
        auto gt = call.find('>', lt == std::string::npos ? 0 : lt + 1);
        if (lt != std::string::npos && gt != std::string::npos && gt > lt + 1) {
            symbol = call.substr(lt + 1, gt - lt - 1);
            auto at = symbol.find('@');
            if (at != std::string::npos)
                symbol = symbol.substr(0, at);
        }

        uint64_t target_addr = 0;
        bool has_target = false;
        if (!symbol.empty()) {
            auto resolved = resolve_symbol_addr(symbol);
            if (resolved) {
                target_addr = *resolved;
                has_target = true;
            } else {
                report.missing_symbols.push_back(symbol);
                if (!allow_stub)
                    continue;
                log::warning("dlsym a échoué pour " + symbol + ", fallback ret");
            }
        }

        if (has_target)
            executor.preload_native_chunk(addr, make_jmp_stub(target_addr));
        else if (allow_stub)
            executor.preload_native_chunk(addr, make_ret_stub());
    }
#else
    (void)meta;
    (void)executor;
    (void)allow_stub;
#endif
    return report;
}

void install_register_trampolines(const PartitionInfo& meta,
                                  FragmentExecutor& executor,
                                  const std::function<std::optional<uint64_t>(const std::string&)>& parse_addr) {
    // Certains externes sont des appels via registre (ex: "rax"). On place un stub "ret" et on
    // charge le registre avec l'adresse du stub pour Ã©viter un saut vers 0x0.
    if (meta.external_calls.empty())
        return;

    uint64_t base = meta.start_address.value_or(0);
    uint64_t stub_start = base + meta.binary_size + 0x100;
    uint64_t cursor = stub_start;

    for (const auto& call : meta.external_calls) {
        // Ignorer les entrÃ©es dÃ©jÃ  traitÃ©es comme adresses.
        auto addr_opt = parse_addr(call);
        if (addr_opt)
            continue;

        if (call.empty())
            continue;

        // CrÃ©er un stub ret unique.
        std::vector<uint8_t> stub = {0xC3};
        executor.preload_native_chunk(cursor, stub);
        // Initialiser le registre pour pointer vers le stub.
        executor.set_input(call, cursor);
        cursor += 0x10;  // espace entre les stubs
    }
}

}  // namespace

NativeRunner::NativeRunner(bool force_native) : force_native_(force_native) {}

bool NativeRunner::run(const ExecutionEntry& entry,
                       FragmentExecutor& executor,
                       ExecutionResult& result) const {
    if (!entry.meta.has_value())
        return false;

    const auto& meta = entry.meta->get();
    preload_dependency_code(meta, executor);
    auto hooks = install_unresolved_hooks(meta, executor, force_native_);
    if (!force_native_ && !hooks.ok()) {
        std::ostringstream oss;
        oss << "Exécution native bloquée: appels externes non résolus.";
        if (!hooks.missing_symbols.empty()) {
            oss << " Symbols: ";
            for (size_t i = 0; i < hooks.missing_symbols.size(); ++i) {
                if (i)
                    oss << ", ";
                oss << hooks.missing_symbols[i];
            }
            oss << ".";
        }
        if (!hooks.unsafe_calls.empty()) {
            oss << " Appels non résolubles: ";
            for (size_t i = 0; i < hooks.unsafe_calls.size(); ++i) {
                if (i)
                    oss << ", ";
                oss << hooks.unsafe_calls[i];
            }
            oss << ".";
        }
        result.error_message = oss.str();
        result.success = false;
        return false;
    }
    install_register_trampolines(meta, executor, parse_addr_token);

    const std::string bin_file = binary_path_from_info(meta);
    std::ifstream file(bin_file, std::ios::binary);
    if (!file) {
        log::error("Impossible d'ouvrir " + bin_file);
        return false;
    }

    std::vector<uint8_t> binary_code((std::istreambuf_iterator<char>(file)),
                                     std::istreambuf_iterator<char>());
    std::optional<uint64_t> original_address = meta.start_address;
    const bool self_recursive = std::find(meta.dependencies.begin(), meta.dependencies.end(), meta.id)
                                != meta.dependencies.end();

    if (binary_code.empty() || is_runtime_partition(meta) || self_recursive)
        binary_code = {0xC3};  // ret de sÃ»retÃ© si le .bin est manquant
    result = executor.execute_native(binary_code, original_address);
    return true;
}

}  // namespace fragment
