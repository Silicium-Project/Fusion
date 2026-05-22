#include "support/Logging.hpp"

namespace fragment::log {

    static constexpr size_t separator_width = 60;

    static void print_line(char fill) {
        std::string line(separator_width, fill);

        std::cout << line << "\n";
    }

    static void print_title(std::string_view title) {
        std::cout << ' ' << title << "\n";
    }

    void banner() {
        std::cout << "\n";

        print_line('=');
        print_title("Fragment Executor");
        print_line('=');
    }

    void section(std::string_view title) {
        std::cout << "\n";

        print_line('=');
        print_title(title);
        print_line('=');
    }

    void subsection(std::string_view title) {
        std::cout << "\n";

        print_line('-');
        print_title(title);
        print_line('-');
    }

    void info(std::string_view message) {
        std::cout << "[INFO] " << message << "\n";
    }

    void warning(std::string_view message) {
        std::cout << "[WARN] " << message << "\n";
    }

    void error(std::string_view message) {
        std::cerr << "[ERROR] " << message << "\n";
    }

}  // namespace fragment::log
