#pragma once

#include <memory>
#include <string>
#include <vector>

#include "splitter/types.hpp"

namespace splitter {

    class Partitioner {
    public:
        explicit Partitioner(std::string binary_path);
        ~Partitioner();

        Partitioner(Partitioner&&) noexcept;
        Partitioner& operator=(Partitioner&&) noexcept;

        Partitioner(const Partitioner&) = delete;
        Partitioner& operator=(const Partitioner&) = delete;

        std::vector<BinaryPartition> run(std::vector<Function>& functions);

    private:
        class Impl;
        std::unique_ptr<Impl> impl_;
    };

    std::vector<BinaryPartition> partition_binary(std::vector<Function>& functions,
                                                const std::string& binary_path);

std::vector<uint8_t> extract_binary_segment(const std::string& binary_path,
                                            uint64_t start_addr, uint64_t end_addr);

std::string function_to_asm(const Function& func);

std::vector<MemorySegment> extract_data_sections(const std::string& binary_path);

}  // namespace splitter
