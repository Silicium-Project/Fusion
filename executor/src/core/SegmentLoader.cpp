#include "core/SegmentLoader.hpp"

#include <elf.h>

namespace fragment {

namespace {

template <typename T>
bool read_struct(std::ifstream& stream, T& value) {
    std::array<char, sizeof(T)> buffer{};
    if (!stream.read(buffer.data(), static_cast<std::streamsize>(buffer.size())))
        return false;
    std::memcpy(&value, buffer.data(), buffer.size());
    return true;
}

}  // namespace

SegmentLoader::SegmentLoader(std::string binary_path)
: binary_path_(std::move(binary_path))
, loaded_(false) {}

void SegmentLoader::set_binary_path(const std::string& path) {
    binary_path_ = path;
    loaded_ = false;
    segments_.clear();
    cache_.clear();
}

const std::string& SegmentLoader::binary_path() const noexcept {
    return binary_path_;
}

bool SegmentLoader::ensure_loaded() const {
    if (loaded_ || binary_path_.empty())
        return loaded_;

    std::ifstream bin(binary_path_, std::ios::binary);
    if (!bin)
        return false;

    Elf64_Ehdr header{};
    if (!read_struct(bin, header) || std::memcmp(header.e_ident, ELFMAG, SELFMAG)
        || header.e_ident[EI_CLASS] != ELFCLASS64)
        return false;

    bin.seekg(header.e_phoff, std::ios::beg);
    segments_.clear();

    for (uint16_t i = 0; i < header.e_phnum; ++i) {
        Elf64_Phdr phdr{};
        if (!read_struct(bin, phdr)) {
            segments_.clear();
            return false;
        }
        if (phdr.p_type == PT_LOAD && phdr.p_filesz > 0) {
            SegmentMapping seg;
            seg.vaddr = phdr.p_vaddr;
            seg.memsz = phdr.p_memsz;
            seg.offset = phdr.p_offset;
            segments_.push_back(seg);
        }
    }

    loaded_ = true;
    return true;
}

std::optional<std::string> SegmentLoader::read_string(uint64_t address) const {
    if (!ensure_loaded())
        return std::nullopt;

    auto it = cache_.find(address);
    if (it != cache_.end())
        return it->second;

    for (const auto& seg : segments_) {
        if (address >= seg.vaddr && address < seg.vaddr + seg.memsz) {
            uint64_t offset = seg.offset + (address - seg.vaddr);
            std::ifstream bin(binary_path_, std::ios::binary);
            if (!bin)
                return std::nullopt;
            bin.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
            std::string value;
            char c;
            std::size_t count = 0;
            while (count++ < 512 && bin.get(c)) {
                if (c == '\0')
                    break;
                value.push_back(c);
            }
            cache_[address] = value;
            return value;
        }
    }

    return std::nullopt;
}

std::vector<uint8_t> SegmentLoader::read_bytes(uint64_t address, size_t max_size) const {
    std::vector<uint8_t> out;
    if (!ensure_loaded() || max_size == 0)
        return out;

    for (const auto& seg : segments_) {
        if (address >= seg.vaddr && address < seg.vaddr + seg.memsz) {
            uint64_t offset = seg.offset + (address - seg.vaddr);
            std::ifstream bin(binary_path_, std::ios::binary);
            if (!bin)
                return out;
            bin.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
            out.resize(max_size);
            bin.read(reinterpret_cast<char*>(out.data()), static_cast<std::streamsize>(max_size));
            out.resize(static_cast<size_t>(bin.gcount()));
            return out;
        }
    }

    return out;
}

}  // namespace fragment
