#include "splitter/types.hpp"

#include <iomanip>
#include <sstream>

namespace splitter {

std::string AsmInstruction::to_string() const {
    std::ostringstream oss;
    oss << "0x" << std::hex << address << ": " << opcode;
    if (!operands.empty()) {
        oss << " " << operands;
    }
    return oss.str();
}

}  // namespace splitter
