#include "core/PrintfEmulator.hpp"

#include <cctype>
#include <iomanip>
#include <sstream>

namespace fragment {

namespace {

uint64_t get_arg(const PrintfArgs& args, std::size_t index) {
    if (index < args.regs.size())
        return args.regs[index];
    std::size_t stack_index = index - args.regs.size();
    if (stack_index < args.stack.size())
        return args.stack[stack_index];
    return 0;
}

std::string apply_width(std::string value, int width, char pad, bool left_align) {
    if (width <= 0 || value.size() >= static_cast<std::size_t>(width))
        return value;
    std::size_t pad_len = static_cast<std::size_t>(width) - value.size();
    if (left_align) {
        value.append(pad_len, ' ');
    } else {
        value.insert(0, pad_len, pad);
    }
    return value;
}

}  // namespace

PrintfArgs gather_printf_args(const RegisterEmulator& emulator, std::size_t max_stack_args) {
    PrintfArgs args{};
    args.fmt = emulator.get("rdi");
    args.regs[0] = emulator.get("rsi");
    args.regs[1] = emulator.get("rdx");
    args.regs[2] = emulator.get("rcx");
    args.regs[3] = emulator.get("r8");
    args.regs[4] = emulator.get("r9");

    uint64_t sp = emulator.get("rsp");
    args.stack.reserve(max_stack_args);
    for (std::size_t i = 0; i < max_stack_args; ++i) {
        args.stack.push_back(emulator.read_qword(sp + static_cast<uint64_t>(i * sizeof(uint64_t))));
    }
    return args;
}

std::string format_printf_like(const std::string& fmt, const PrintfArgs& args, const ReadStringFunc& read_string) {
    std::ostringstream out;
    std::size_t arg_idx = 0;
    const std::size_t total_args = args.regs.size() + args.stack.size();

    for (std::size_t i = 0; i < fmt.size(); ++i) {
        char c = fmt[i];
        if (c != '%') {
            out << c;
            continue;
        }
        if (i + 1 < fmt.size() && fmt[i + 1] == '%') {
            out << '%';
            ++i;
            continue;
        }

        bool left_align = false;
        bool zero_pad = false;
        std::size_t j = i + 1;
        while (j < fmt.size()) {
            if (fmt[j] == '-') {
                left_align = true;
                ++j;
                continue;
            }
            if (fmt[j] == '0') {
                zero_pad = true;
                ++j;
                continue;
            }
            if (fmt[j] == '+' || fmt[j] == ' ' || fmt[j] == '#') {
                ++j;
                continue;
            }
            break;
        }

        int width = 0;
        while (j < fmt.size() && std::isdigit(static_cast<unsigned char>(fmt[j]))) {
            width = width * 10 + (fmt[j] - '0');
            ++j;
        }

        int precision = -1;
        if (j < fmt.size() && fmt[j] == '.') {
            ++j;
            precision = 0;
            while (j < fmt.size() && std::isdigit(static_cast<unsigned char>(fmt[j]))) {
                precision = precision * 10 + (fmt[j] - '0');
                ++j;
            }
        }

        bool is_long = false;
        bool is_long_long = false;
        if (j + 1 < fmt.size() && fmt[j] == 'l' && fmt[j + 1] == 'l') {
            is_long_long = true;
            j += 2;
        } else if (j < fmt.size() && fmt[j] == 'l') {
            is_long = true;
            ++j;
        }
        if (j >= fmt.size())
            break;

        char spec = fmt[j];
        if (arg_idx >= total_args) {
            out << '%' << spec;
            i = j;
            continue;
        }

        uint64_t val = get_arg(args, arg_idx++);
        std::string value_str;

        if (spec == 'x' || spec == 'X') {
            std::ostringstream val_ss;
            val_ss << std::hex << (spec == 'X' ? std::uppercase : std::nouppercase);
            if (!is_long && !is_long_long)
                val &= 0xFFFFFFFFu;
            val_ss << val;
            value_str = val_ss.str();
            value_str = apply_width(value_str, width, zero_pad && !left_align ? '0' : ' ', left_align);
        } else if (spec == 'u' || spec == 'd') {
            std::ostringstream val_ss;
            if (!is_long && !is_long_long) {
                if (spec == 'd')
                    val_ss << static_cast<int32_t>(val);
                else
                    val_ss << static_cast<uint32_t>(val);
            } else {
                if (spec == 'd')
                    val_ss << static_cast<int64_t>(val);
                else
                    val_ss << static_cast<uint64_t>(val);
            }
            value_str = val_ss.str();
            value_str = apply_width(value_str, width, zero_pad && !left_align ? '0' : ' ', left_align);
        } else if (spec == 'p') {
            std::ostringstream val_ss;
            val_ss << "0x" << std::hex << std::nouppercase << val;
            value_str = val_ss.str();
            value_str = apply_width(value_str, width, ' ', left_align);
        } else if (spec == 's') {
            if (val == 0) {
                value_str = "(null)";
            } else if (read_string) {
                auto text = read_string(val);
                if (text)
                    value_str = *text;
                else {
                    std::ostringstream val_ss;
                    val_ss << "0x" << std::hex << val;
                    value_str = val_ss.str();
                }
            }
            if (precision >= 0 && static_cast<std::size_t>(precision) < value_str.size())
                value_str.resize(static_cast<std::size_t>(precision));
            value_str = apply_width(value_str, width, ' ', left_align);
        } else if (spec == 'c') {
            value_str.assign(1, static_cast<char>(val & 0xFF));
            value_str = apply_width(value_str, width, ' ', left_align);
        } else {
            out << '%' << spec;
            i = j;
            continue;
        }

        out << value_str;
        i = j;
    }
    return out.str();
}

}  // namespace fragment
