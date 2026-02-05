#include "partitioning/BinaryExtractor.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <regex>
#include <sstream>
#include <string>

#include "support/ShellCommand.hpp"

namespace splitter {

BinaryExtractor::~BinaryExtractor() = default;

std::vector<uint8_t> BinaryExtractor::ExtractSegment(const std::string& binary_path,
                                                     uint64_t start_addr,
                                                     uint64_t end_addr) const {
    std::vector<uint8_t> result;
    try {
        if (end_addr <= start_addr)
            return result;

        std::error_code ec;
        const auto size = std::filesystem::file_size(binary_path, ec);
        if (!ec && size == 0)
            return result;

        std::string cmd = "readelf -W -S " + ShellQuote(binary_path);
        std::string output = ExecCommand(cmd);
        std::regex section_pattern(
            "\\[\\s*\\d+\\]\\s+([^\\s]+)\\s+([^\\s]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)");
        std::smatch match;

        struct SectionInfo {
            std::string name;
            uint64_t vaddr = 0;
            uint64_t offset = 0;
            uint64_t size = 0;
        };
        std::vector<SectionInfo> sections;

        std::istringstream stream(output);
        std::string line;
        while (std::getline(stream, line)) {
            if (!std::regex_search(line, match, section_pattern))
                continue;
            SectionInfo info;
            info.name = match[1].str();
            info.vaddr = std::stoull(match[3].str(), nullptr, 16);
            info.offset = std::stoull(match[4].str(), nullptr, 16);
            info.size = std::stoull(match[5].str(), nullptr, 16);
            sections.push_back(std::move(info));
        }

        if (sections.empty())
            return result;

        const SectionInfo* section = nullptr;
        for (const auto& sec : sections) {
            if (sec.size == 0)
                continue;
            if (start_addr >= sec.vaddr && start_addr < sec.vaddr + sec.size) {
                section = &sec;
                break;
            }
        }
        if (!section)
            return result;

        std::ifstream file(binary_path, std::ios::binary);
        if (!file)
            return result;

        const uint64_t clamped_end = std::min(end_addr, section->vaddr + section->size);
        uint64_t file_start = section->offset + (start_addr - section->vaddr);
        uint64_t file_end = section->offset + (clamped_end - section->vaddr);
        if (file_end <= file_start)
            return result;

        file.seekg(file_start);
        const size_t segment_size = static_cast<size_t>(file_end - file_start);
        const size_t kMaxSegment = 16 * 1024 * 1024;  // 16 Mo max pour ?viter les d?passements.
        if (segment_size == 0 || segment_size > kMaxSegment)
            return result;
        std::vector<char> buffer(segment_size);
        file.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto read_bytes = static_cast<size_t>(file.gcount());
        if (read_bytes == 0)
            return result;
        result.assign(buffer.begin(), buffer.begin() + static_cast<std::ptrdiff_t>(read_bytes));
    } catch (const std::exception& e) {
        std::cerr << "Avertissement: impossible d'extraire segment: " << e.what() << "\n";
    }
    return result;
}

std::vector<MemorySegment> BinaryExtractor::ExtractDataSections(const std::string& binary_path) const {
    std::vector<MemorySegment> segments;

    try {
        std::error_code ec;
        const auto size = std::filesystem::file_size(binary_path, ec);
        if (!ec && size == 0)
            return segments;

        std::string cmd = "readelf -W -S " + ShellQuote(binary_path);
        std::string output = ExecCommand(cmd);
        std::regex section_pattern(
            "\\[\\s*\\d+\\]\\s+([^\\s]+)\\s+([^\\s]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)");
        std::smatch match;

        std::ifstream file(binary_path, std::ios::binary);
        std::istringstream stream(output);
        std::string line;

        while (std::getline(stream, line)) {
            if (!std::regex_search(line, match, section_pattern))
                continue;

            std::string name = match[1].str();
            std::string type = match[2].str();

            const bool is_data = name.find(".data") != std::string::npos;
            const bool is_bss = name.find(".bss") != std::string::npos;
            const bool is_got = name.find(".got") != std::string::npos;
            const bool is_plt = name.find(".plt") != std::string::npos;
            const bool is_rodata = name.find(".rodata") != std::string::npos;
            if (!is_data && !is_bss && !is_got && !is_plt && !is_rodata)
                continue;

            uint64_t addr = std::stoull(match[3].str(), nullptr, 16);
            uint64_t offset = std::stoull(match[4].str(), nullptr, 16);
            uint64_t size = std::stoull(match[5].str(), nullptr, 16);

            MemorySegment segment;
            segment.SetName(name);
            segment.SetAddress(addr);

            if (type == "NOBITS") {
                segment.Bytes().resize(size, 0);
            } else if (size != 0) {
                segment.Bytes().resize(size);
                if (file) {
                    file.seekg(static_cast<std::streamoff>(offset));
                    file.read(reinterpret_cast<char*>(segment.Bytes().data()), static_cast<std::streamsize>(size));
                    const auto read_bytes = static_cast<size_t>(file.gcount());
                    if (read_bytes < segment.Bytes().size())
                        segment.Bytes().resize(read_bytes);
                }
            }

            segments.push_back(std::move(segment));
        }
    } catch (const std::exception& e) {
        std::cerr << "Avertissement: impossible d'extraire les sections de donn?es: " << e.what() << "\n";
    }

    return segments;
}

}  // namespace splitter
