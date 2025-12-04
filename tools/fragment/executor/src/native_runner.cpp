#include "fragment/native_runner.hpp"

#include "fragment/logging.hpp"
#include "fragment/partition_registry.hpp"
#include "fragment/partition_summary.hpp"
#include "fragment/utils.hpp"

#include <fstream>
#include <iterator>
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
                     + " pour initialiser les dépendances natives.");
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
                log::warning("Partition dépendante inconnue: " + dep_id);
                continue;
            }
            const PartitionInfo& dep_meta = dep->get();
            if (!dep_meta.start_address.has_value()) {
                log::warning("Adresse de départ manquante pour la partition dépendante: " + dep_id);
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

void install_unresolved_hooks(const PartitionInfo& meta, FragmentExecutor& executor) {
#ifdef __linux__
    for (const auto& call : meta.unresolved_calls) {
        auto info = parse_unresolved_descriptor(call);
        if (!info)
            continue;
        void* target = dlsym(RTLD_DEFAULT, info->symbol.c_str());
        if (!target)
            continue;
        uint64_t fn_addr = reinterpret_cast<uint64_t>(target);
        std::vector<uint8_t> stub;
        stub.reserve(12);
        stub.push_back(0x48);
        stub.push_back(0xB8);
        for (size_t idx = 0; idx < 8; ++idx)
            stub.push_back(static_cast<uint8_t>((fn_addr >> (idx * 8)) & 0xFF));
        stub.push_back(0xFF);
        stub.push_back(0xE0);
        executor.preload_native_chunk(info->address, stub);
    }
#else
    (void)meta;
    (void)executor;
#endif
}

}  // namespace

NativeRunner::NativeRunner(bool force_native) : force_native_(force_native) {}

bool NativeRunner::run(const ExecutionEntry& entry,
                       FragmentExecutor& executor,
                       ExecutionResult& result) const {
    if (!entry.meta.has_value())
        return false;

    const auto& meta = entry.meta->get();
    const bool has_calls = !meta.unresolved_calls.empty();
    const bool has_deps = !meta.dependencies.empty();

    if (!force_native_ && (has_calls || has_deps)) {
        log::warning("Repli émulation : appels externes/dépendances détectés sur " + entry.name);
        return false;
    }

    preload_dependency_code(meta, executor);
    install_unresolved_hooks(meta, executor);

    const std::string bin_file = derive_binary_path(entry);
    std::ifstream file(bin_file, std::ios::binary);
    if (!file) {
        log::error("Impossible d'ouvrir " + bin_file);
        return false;
    }

    std::vector<uint8_t> binary_code((std::istreambuf_iterator<char>(file)),
                                     std::istreambuf_iterator<char>());
    std::optional<uint64_t> original_address = meta.start_address;
    result = executor.execute_native(binary_code, original_address);
    return true;
}

}  // namespace fragment
