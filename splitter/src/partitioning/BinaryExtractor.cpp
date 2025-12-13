#include "partitioning/BinaryExtractor.hpp"

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
        std::string cmd = "readelf -W -S " + binary_path;
        std::string output = ExecCommand(cmd);
        std::regex section_pattern(
            "\\[\\s*\\d+\\]\\s+([^\\s]+)\\s+([^\\s]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)");
        std::smatch match;

        uint64_t text_offset = 0;
        uint64_t text_vaddr = 0;
        bool found_text = false;

        std::istringstream stream(output);
        std::string line;
        while (std::getline(stream, line)) {
            if (std::regex_search(line, match, section_pattern)
                && match[1].str().find(".text") != std::string::npos) {
                text_vaddr = std::stoull(match[3].str(), nullptr, 16);
                text_offset = std::stoull(match[4].str(), nullptr, 16);
                found_text = true;
                break;
            }
        }

        if (!found_text || end_addr <= start_addr || start_addr < text_vaddr)
            return result;

        std::ifstream file(binary_path, std::ios::binary);
        if (!file)
            return result;

        uint64_t file_start = text_offset + (start_addr - text_vaddr);
        uint64_t file_end = text_offset + (end_addr - text_vaddr);
        if (file_end <= file_start)
            return result;

        file.seekg(file_start);
        const size_t segment_size = static_cast<size_t>(file_end - file_start);
        const size_t kMaxSegment = 16 * 1024 * 1024;  // 16 Mo max pour éviter les dépassements.
        if (segment_size == 0 || segment_size > kMaxSegment)
            return result;
        std::vector<char> buffer(segment_size);
        file.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        result.assign(buffer.begin(), buffer.end());
    } catch (const std::exception& e) {
        std::cerr << "Avertissement: impossible d'extraire segment: " << e.what() << "\n";
    }
    return result;
}

std::vector<MemorySegment> BinaryExtractor::ExtractDataSections(const std::string& binary_path) const {
    std::vector<MemorySegment> segments;

    try {
        std::string cmd = "readelf -W -S " + binary_path;
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
                }
            }

            if (!segment.Bytes().empty())
                segments.push_back(std::move(segment));
        }
    } catch (const std::exception& e) {
        std::cerr << "Avertissement: impossible d'extraire les sections de données: " << e.what() << "\n";
    }

    return segments;
}

}  // namespace splitter
