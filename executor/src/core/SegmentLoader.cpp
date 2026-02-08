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

bool seek_and_read(std::ifstream& stream, uint64_t offset, void* dst, size_t size) {
    stream.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
    if (!stream)
        return false;
    return static_cast<bool>(stream.read(reinterpret_cast<char*>(dst), static_cast<std::streamsize>(size)));
}

struct PeFileHeader {
    uint16_t machine;
    uint16_t number_of_sections;
    uint32_t time_date_stamp;
    uint32_t pointer_to_symbol_table;
    uint32_t number_of_symbols;
    uint16_t size_of_optional_header;
    uint16_t characteristics;
};

struct PeSectionHeader {
    char name[8];
    uint32_t virtual_size;
    uint32_t virtual_address;
    uint32_t size_of_raw_data;
    uint32_t pointer_to_raw_data;
    uint32_t pointer_to_relocations;
    uint32_t pointer_to_linenumbers;
    uint16_t number_of_relocations;
    uint16_t number_of_linenumbers;
    uint32_t characteristics;
};

constexpr uint16_t kPe32PlusMagic = 0x20b;
constexpr uint32_t kPeSignature = 0x00004550;  // "PE\0\0" little-endian
constexpr uint32_t kImageScnMemExecute = 0x20000000u;
constexpr uint32_t kImageScnMemRead = 0x40000000u;
constexpr uint32_t kImageScnMemWrite = 0x80000000u;

}  // namespace

SegmentLoader::SegmentLoader(std::string binary_path)
: binary_path_(std::move(binary_path))
, loaded_(false) {}

void SegmentLoader::set_binary_path(const std::string& path) {
    binary_path_ = path;
    loaded_ = false;
    format_ = BinaryFormat::Unknown;
    entrypoint_.reset();
    last_error_.clear();
    segments_.clear();
    cache_.clear();
}

const std::string& SegmentLoader::binary_path() const noexcept {
    return binary_path_;
}

SegmentLoader::BinaryFormat SegmentLoader::format() const noexcept {
    return format_;
}

std::optional<uint64_t> SegmentLoader::entrypoint() const noexcept {
    return entrypoint_;
}

const std::string& SegmentLoader::last_error() const noexcept {
    return last_error_;
}

void SegmentLoader::set_error(const std::string& message) const {
    last_error_ = message;
}

bool SegmentLoader::load_elf(std::ifstream& bin) const {
    Elf64_Ehdr header{};
    if (!read_struct(bin, header)
        || std::memcmp(header.e_ident, ELFMAG, SELFMAG)
        || header.e_ident[EI_CLASS] != ELFCLASS64) {
        set_error("invalid ELF64 header");
        return false;
    }

    entrypoint_ = header.e_entry;

    bin.seekg(header.e_phoff, std::ios::beg);
    segments_.clear();

    for (uint16_t i = 0; i < header.e_phnum; ++i) {
        Elf64_Phdr phdr{};
        if (!read_struct(bin, phdr)) {
            segments_.clear();
            set_error("truncated ELF program header");
            return false;
        }
        if (phdr.p_type != PT_LOAD || phdr.p_memsz == 0)
            continue;

        SegmentMapping seg;
        seg.vaddr = phdr.p_vaddr;
        seg.memsz = phdr.p_memsz;
        seg.offset = phdr.p_offset;
        seg.filesz = phdr.p_filesz;
        seg.readable = (phdr.p_flags & PF_R) != 0;
        seg.writable = (phdr.p_flags & PF_W) != 0;
        seg.executable = (phdr.p_flags & PF_X) != 0;
        segments_.push_back(seg);
    }

    if (segments_.empty()) {
        set_error("no loadable ELF segments");
        return false;
    }
    return true;
}

bool SegmentLoader::load_pe(std::ifstream& bin) const {
    uint32_t pe_offset = 0;
    if (!seek_and_read(bin, 0x3c, &pe_offset, sizeof(pe_offset))) {
        set_error("invalid PE DOS header");
        return false;
    }

    uint32_t signature = 0;
    if (!seek_and_read(bin, pe_offset, &signature, sizeof(signature)) || signature != kPeSignature) {
        set_error("invalid PE signature");
        return false;
    }

    PeFileHeader file_header{};
    const uint64_t file_header_offset = static_cast<uint64_t>(pe_offset) + 4u;
    if (!seek_and_read(bin, file_header_offset, &file_header, sizeof(file_header))) {
        set_error("truncated PE file header");
        return false;
    }

    const uint64_t optional_header_offset = file_header_offset + sizeof(file_header);
    uint16_t optional_magic = 0;
    if (!seek_and_read(bin, optional_header_offset, &optional_magic, sizeof(optional_magic))) {
        set_error("missing PE optional header");
        return false;
    }
    if (optional_magic != kPe32PlusMagic) {
        set_error("unsupported PE format: expected PE32+");
        return false;
    }

    uint32_t entry_rva = 0;
    uint64_t image_base = 0;
    uint32_t size_of_headers = 0;
    uint32_t number_of_rva_and_sizes = 0;
    if (!seek_and_read(bin, optional_header_offset + 16u, &entry_rva, sizeof(entry_rva))
        || !seek_and_read(bin, optional_header_offset + 24u, &image_base, sizeof(image_base))
        || !seek_and_read(bin, optional_header_offset + 60u, &size_of_headers, sizeof(size_of_headers))
        || !seek_and_read(bin, optional_header_offset + 108u, &number_of_rva_and_sizes,
                          sizeof(number_of_rva_and_sizes))) {
        set_error("truncated PE optional header");
        return false;
    }

    if (number_of_rva_and_sizes > 1) {
        uint32_t import_rva = 0;
        uint32_t import_size = 0;
        if (!seek_and_read(bin, optional_header_offset + 120u, &import_rva, sizeof(import_rva))
            || !seek_and_read(bin, optional_header_offset + 124u, &import_size, sizeof(import_size))) {
            set_error("truncated PE import directory");
            return false;
        }
        if (import_rva != 0 && import_size != 0) {
            set_error("unsupported PE feature: import table present");
            return false;
        }
    }

    segments_.clear();
    if (size_of_headers > 0) {
        SegmentMapping headers;
        headers.vaddr = image_base;
        headers.memsz = size_of_headers;
        headers.offset = 0;
        headers.filesz = size_of_headers;
        headers.readable = true;
        segments_.push_back(headers);
    }

    const uint64_t section_offset = optional_header_offset + file_header.size_of_optional_header;
    for (uint16_t i = 0; i < file_header.number_of_sections; ++i) {
        PeSectionHeader section{};
        const uint64_t current_offset = section_offset + static_cast<uint64_t>(i) * sizeof(PeSectionHeader);
        if (!seek_and_read(bin, current_offset, &section, sizeof(section))) {
            set_error("truncated PE section table");
            segments_.clear();
            return false;
        }

        const uint64_t mem_size = section.virtual_size ? section.virtual_size : section.size_of_raw_data;
        if (mem_size == 0)
            continue;

        SegmentMapping seg;
        seg.vaddr = image_base + section.virtual_address;
        seg.memsz = mem_size;
        seg.offset = section.pointer_to_raw_data;
        seg.filesz = section.size_of_raw_data;
        seg.readable = (section.characteristics & kImageScnMemRead) != 0;
        seg.writable = (section.characteristics & kImageScnMemWrite) != 0;
        seg.executable = (section.characteristics & kImageScnMemExecute) != 0;
        segments_.push_back(seg);
    }

    if (segments_.empty()) {
        set_error("no loadable PE sections");
        return false;
    }
    entrypoint_ = image_base + entry_rva;
    return true;
}

bool SegmentLoader::ensure_loaded() const {
    if (loaded_ || binary_path_.empty())
        return loaded_;

    format_ = BinaryFormat::Unknown;
    entrypoint_.reset();
    last_error_.clear();
    segments_.clear();
    cache_.clear();

    std::ifstream bin(binary_path_, std::ios::binary);
    if (!bin) {
        set_error("unable to open binary file");
        return false;
    }

    std::array<uint8_t, 4> magic{};
    if (!bin.read(reinterpret_cast<char*>(magic.data()), static_cast<std::streamsize>(magic.size()))) {
        set_error("unable to read binary magic");
        return false;
    }

    bool ok = false;
    if (magic[0] == 0x7f && magic[1] == 'E' && magic[2] == 'L' && magic[3] == 'F') {
        format_ = BinaryFormat::Elf64;
        bin.clear();
        bin.seekg(0, std::ios::beg);
        ok = load_elf(bin);
    } else if (magic[0] == 'M' && magic[1] == 'Z') {
        format_ = BinaryFormat::Pe32Plus;
        bin.clear();
        bin.seekg(0, std::ios::beg);
        ok = load_pe(bin);
    } else {
        set_error("unsupported binary format");
        return false;
    }

    loaded_ = ok;
    return ok;
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
            const uint64_t max_file_offset = seg.offset + seg.filesz;
            if (offset >= max_file_offset)
                return std::string();
            std::ifstream bin(binary_path_, std::ios::binary);
            if (!bin)
                return std::nullopt;
            bin.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
            std::string value;
            char c;
            std::size_t count = 0;
            while (count++ < 512 && static_cast<uint64_t>(offset + count) <= max_file_offset && bin.get(c)) {
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
            const uint64_t max_file_offset = seg.offset + seg.filesz;
            if (offset >= max_file_offset)
                return out;
            const uint64_t remaining = max_file_offset - offset;
            const size_t to_read = std::min<std::size_t>(max_size, static_cast<size_t>(remaining));
            std::ifstream bin(binary_path_, std::ios::binary);
            if (!bin)
                return out;
            bin.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
            out.resize(to_read);
            bin.read(reinterpret_cast<char*>(out.data()), static_cast<std::streamsize>(to_read));
            out.resize(static_cast<size_t>(bin.gcount()));
            return out;
        }
    }

    return out;
}

}  // namespace fragment
