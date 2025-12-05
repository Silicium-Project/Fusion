#pragma once

#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "splitter/pipeline/IReporter.hpp"
#include "splitter/core/Function.hpp"
#include "splitter/core/Partition.hpp"

namespace splitter {

class ConsoleReporter : public IReporter {
public:
    enum class Color { Green, Cyan, Yellow, Reset };

    ConsoleReporter() = default;

    void Banner(const std::string& title) override {
        std::cout << Colorize(title, Color::Cyan) << "\n\n";
    }

    void Info(const std::string& message) override {
        std::cout << message << "\n";
    }

    void ReportFunctions(const std::vector<Function>& functions, std::size_t preview) override {
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

    void ReportLoops(std::vector<Function>& functions, std::size_t preview) override {
        std::vector<std::reference_wrapper<Function>> loop_functions;
        for (auto& func : functions)
            if (func.IsLoop())
                loop_functions.push_back(func);

        const size_t count = std::min(preview, loop_functions.size());
        for (size_t i = 0; i < count; ++i) {
            const Function& func = loop_functions[i];
            auto loop_info = X86InstructionAnalyzer::Instance().DetectLoopPatterns(func);
            std::string status = loop_info.parallelizable ? "PARALLÉLISABLE" : "SÉQUENTIELLE";
            std::ostringstream line;
            line << "  " << std::left << std::setw(30) << func.Name() << " - " << status;
            std::cout << Colorize(line.str(), loop_info.parallelizable ? Color::Green : Color::Yellow) << "\n";
            if (!loop_info.reason.empty())
                std::cout << "    Raison: " << loop_info.reason << "\n";
        }
    }

    void ReportPartition(const Partition& partition, std::size_t sample_preview) override {
        std::string status = partition.IsParallelizable() ? "PARALLÈLE" : "SÉQUENTIEL";
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

private:
    template <typename Container>
    void PrintSample(const std::string& label, const Container& container, std::size_t limit) {
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

    std::string Colorize(const std::string& text, Color color) const {
        switch (color) {
            case Color::Green: return "\033[32m" + text + "\033[0m";
            case Color::Cyan: return "\033[36m" + text + "\033[0m";
            case Color::Yellow: return "\033[33m" + text + "\033[0m";
            case Color::Reset: default: return text;
        }
    }
};

}  // namespace splitter
