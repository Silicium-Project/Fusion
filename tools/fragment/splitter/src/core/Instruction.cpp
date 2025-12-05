#include "core/Instruction.hpp"

#include <iomanip>
#include <sstream>

namespace splitter {

std::string Instruction::ToString() const {
    std::ostringstream oss;
    oss << "0x" << std::hex << address_ << ": " << opcode_;
    if (!operands_.empty())
        oss << " " << operands_;
    return oss.str();
}

}  // namespace splitter
