#pragma once

#include <iosfwd>

#include "worker/core/WorkerReport.hpp"

namespace worker {

enum class OutputFormat {
    Text,
    Json
};

class Reporter {
public:
    Reporter(OutputFormat format, std::ostream& stream);

    void emit(const WorkerReport& report);

private:
    OutputFormat format_;
    std::ostream* stream_;

    void emit_text(const WorkerReport& report);
    void emit_json(const WorkerReport& report);
};

}  // namespace worker
