#pragma once

#include <string>

#include "analysis/IDisassembler.hpp"
#include "support/SystemContext.hpp"

namespace splitter {

class ObjdumpDisassembler : public IDisassembler {
public:
    explicit ObjdumpDisassembler(std::string binary_path,
                                 SystemContext system = DefaultSystemContext());

    std::pair<std::vector<Function>, std::string> Run() const override;
    static std::vector<Function> ParseOutput(const std::string& output);

private:
    std::string binary_path_;
    SystemContext system_;
};

}  // namespace splitter
