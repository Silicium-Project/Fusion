#include "pipeline/ConsoleReporter.hpp"

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace splitter {

void ConsoleReporter::Banner(const std::string& title) {
    std::cout << Colorize(title, Color::Cyan) << "\n\n";
}

void ConsoleReporter::Info(const std::string& message) {
    std::cout << message << "\n";
}

void ConsoleReporter::ReportTiming(const std::string& phase, long long milliseconds) {
    std::ostringstream line;
    line << "[" << phase << "] " << milliseconds << " ms";
    std::cout << line.str() << "\n";
}

void ConsoleReporter::ReportFunctions(const std::vector<Function>& functions, std::size_t preview) {
    const size_t count = std::min(preview, functions.size());
    for (size_t i = 0; i < count; ++i) {
        const auto& func = functions[i];
        uint64_t size = func.EndAddr() - func.StartAddr();
        std::ostringstream line;
        line << "  " << std::left << std::setw(30) << func.Name()
             << " @ 0x" << std::hex << std::setw(10) << func.StartAddr()
             << std::dec << " (" << std::setw(4) << func.Instructions().size()
             << " insts, " << std::setw(5) << size << " bytes)";
        std::cout << line.str() << "\n";
    }
    if (functions.size() > preview)
        std::cout << Colorize("  ... (" + std::to_string(functions.size() - preview) + " autres fonctions)",
                              Color::Yellow)
                  << "\n";
}

void ConsoleReporter::ReportLoops(std::vector<Function>& functions, std::size_t preview) {
    std::vector<std::reference_wrapper<Function>> loop_functions;
    for (auto& func : functions)
        if (func.IsLoop())
            loop_functions.push_back(func);

    const size_t count = std::min(preview, loop_functions.size());
    for (size_t i = 0; i < count; ++i) {
        const Function& func = loop_functions[i];
        const auto& loop_info = func.LoopAnalysisInfo();
        std::string status = "INCONNU";
        if (loop_info.has_value())
            status = loop_info->parallelizable ? "PARALL?LISABLE" : "S?QUENTIELLE";
        std::ostringstream line;
        line << "  " << std::left << std::setw(30) << func.Name() << " - " << status;
        const Color color = loop_info.has_value()
            ? (loop_info->parallelizable ? Color::Green : Color::Yellow)
            : Color::Yellow;
        std::cout << Colorize(line.str(), color) << "\n";
        if (loop_info.has_value() && !loop_info->reason.empty())
            std::cout << "    Raison: " << loop_info->reason << "\n";
    }
}

void ConsoleReporter::ReportPartition(const Partition& partition, std::size_t sample_preview) {
    std::string status = partition.IsParallelizable() ? "PARALL?LE" : "S?QUENTIEL";
    std::ostringstream header;
    header << "\nPartition: " << partition.Id() << " (" << status << ")";
    std::cout << Colorize(header.str(), partition.IsParallelizable() ? Color::Green : Color::Yellow) << "\n";

    std::ostringstream addr;
    addr << "  Adresse: 0x" << std::hex << partition.StartAddr()
         << " - 0x" << partition.EndAddr();
    std::cout << addr.str() << std::dec << "\n";
    std::cout << "  Taille: " << partition.RawBytes().size() << " bytes\n";

    PrintSample("Inputs", partition.Inputs(), sample_preview);
    PrintSample("Inputs externes", partition.ExternalInputs(), sample_preview);
    PrintSample("Outputs", partition.Outputs(), sample_preview);
}

std::string ConsoleReporter::Colorize(const std::string& text, Color color) const {
    switch (color) {
        case Color::Green: return "\033[32m" + text + "\033[0m";
        case Color::Cyan: return "\033[36m" + text + "\033[0m";
        case Color::Yellow: return "\033[33m" + text + "\033[0m";
        case Color::Reset:
        default: return text;
    }
}

template <typename Container>
void ConsoleReporter::PrintSample(const std::string& label, const Container& container, std::size_t limit) {
    std::cout << "  " << label << ": ";
    size_t count = 0;
    for (const auto& item : container) {
        if (count++ >= limit) {
            std::cout << "...";
            break;
        }
        std::cout << item << " ";
    }
    std::cout << "\n";
}

// Explicit instantiations for the container types we use.
template void ConsoleReporter::PrintSample<FlatStringSet>(const std::string&, const FlatStringSet&, std::size_t);
template void ConsoleReporter::PrintSample<std::vector<std::string>>(const std::string&,
                                                                    const std::vector<std::string>&,
                                                                    std::size_t);

}  // namespace splitter
