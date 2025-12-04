#pragma once

#include "fragment/common.hpp"

namespace fragment {

    class SegmentLoader {
        public:
            explicit SegmentLoader(std::string binary_path = {});

            void set_binary_path(const std::string& path);
            [[nodiscard]] const std::string& binary_path() const noexcept;

            bool ensure_loaded() const;
            std::optional<std::string> read_string(uint64_t address) const;

        private:
            struct SegmentMapping {
                uint64_t vaddr = 0;
                uint64_t memsz = 0;
                uint64_t offset = 0;
            };

            std::string binary_path_;
            mutable bool loaded_;
            mutable std::vector<SegmentMapping> segments_;
            mutable std::unordered_map<uint64_t, std::string> cache_;
    };

}  // namespace fragment
