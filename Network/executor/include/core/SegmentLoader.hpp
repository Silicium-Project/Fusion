#pragma once

#include "core/Common.hpp"

namespace fragment {

    class SegmentLoader {
        public:
            enum class BinaryFormat {
                Unknown,
                Elf64,
                Pe32Plus
            };

            explicit SegmentLoader(std::string binary_path = {});

            void set_binary_path(const std::string& path);
            [[nodiscard]] const std::string& binary_path() const noexcept;
            [[nodiscard]] BinaryFormat format() const noexcept;
            [[nodiscard]] std::optional<uint64_t> entrypoint() const noexcept;
            [[nodiscard]] const std::string& last_error() const noexcept;

            bool ensure_loaded() const;
            std::optional<std::string> read_string(uint64_t address) const;
            std::vector<uint8_t> read_bytes(uint64_t address, size_t max_size) const;

        private:
            struct SegmentMapping {
                uint64_t vaddr = 0;
                uint64_t memsz = 0;
                uint64_t offset = 0;
                uint64_t filesz = 0;
                bool readable = true;
                bool writable = false;
                bool executable = false;
            };

            bool load_elf(std::ifstream& bin) const;
            bool load_pe(std::ifstream& bin) const;
            void set_error(const std::string& message) const;

            std::string binary_path_;
            mutable bool loaded_;
            mutable BinaryFormat format_ = BinaryFormat::Unknown;
            mutable std::optional<uint64_t> entrypoint_;
            mutable std::string last_error_;
            mutable std::vector<SegmentMapping> segments_;
            mutable std::unordered_map<uint64_t, std::string> cache_;
    };

}  // namespace fragment
