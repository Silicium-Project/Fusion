#pragma once

#include <map>
#include <utility>

#include "core/Common.hpp"
#include "core/Memory.hpp"

namespace fragment {

struct FdCapture {
    std::string data;
    std::string alias;
};

class IFdView {
public:
    virtual ~IFdView() = default;
    virtual bool empty() const = 0;
    virtual size_t size() const = 0;
    virtual const std::map<int, FdCapture>& entries() const = 0;
    virtual bool contains(int fd) const = 0;
    virtual const FdCapture& at(int fd) const = 0;
};

class IFdStore : public IFdView {
public:
    ~IFdStore() override = default;
    virtual void set(int fd, FdCapture capture) = 0;
    virtual FdCapture& operator[](int fd) = 0;
    virtual FdCapture& at(int fd) = 0;
};

class FdTable : public IFdStore {
public:
    using Map = std::map<int, FdCapture>;

    bool empty() const override;
    size_t size() const override;
    const Map& entries() const override;
    bool contains(int fd) const override;
    void set(int fd, FdCapture capture) override;
    FdCapture& operator[](int fd) override;
    const FdCapture& at(int fd) const override;
    FdCapture& at(int fd) override;
    size_t count(int fd) const;

    Map::const_iterator begin() const;
    Map::const_iterator end() const;

private:
    Map entries_;
};

struct ExecutionResult {
    bool success = false;
    std::string error_message;
    std::map<std::string, uint64_t> initial_regs;
    std::map<std::string, uint64_t> final_regs;
    std::map<std::string, std::pair<uint64_t, uint64_t>> changed_regs;
    size_t instructions_executed = 0;
    size_t memory_accesses = 0;
    std::string program_stdout;
    std::string program_stderr;
    FdTable fd_outputs;             // captures des FD + alias
    std::vector<MemoryPatch> memory_patches;

    void print() const;
};

}  // namespace fragment
