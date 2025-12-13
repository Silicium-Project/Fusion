#include "pipeline/JsonReporter.hpp"

#include <iomanip>
#include <sstream>

namespace splitter {

namespace {

std::string Escape(const std::string& text) {
    std::ostringstream oss;
    for (char c : text) {
        switch (c) {
            case '\"': oss << "\\\""; break;
            case '\\': oss << "\\\\"; break;
            case '\n': oss << "\\n"; break;
            case '\r': oss << "\\r"; break;
            case '\t': oss << "\\t"; break;
            default: oss << c; break;
        }
    }
    return oss.str();
}

}  // namespace

namespace {

std::shared_ptr<std::ostream> StdOutPtr() {
    return std::shared_ptr<std::ostream>(&std::cout, [](std::ostream*) {});
}

}  // namespace

JsonReporter::JsonReporter(std::shared_ptr<std::ostream> out)
    : out_(out ? std::move(out) : StdOutPtr()) {}

void JsonReporter::Banner(const std::string& title) {
    *out_ << R"({"type":"banner","title":")" << Escape(title) << "\"}\n";
}

void JsonReporter::Info(const std::string& message) {
    *out_ << R"({"type":"info","message":")" << Escape(message) << "\"}\n";
}

void JsonReporter::ReportTiming(const std::string& phase, long long milliseconds) {
    *out_ << R"({"type":"timing","phase":")" << Escape(phase) << R"(","ms":)" << milliseconds << "}\n";
}

void JsonReporter::ReportFunctions(const std::vector<Function>& functions, std::size_t preview) {
    *out_ << R"({"type":"functions","count":)" << functions.size() << R"(,"preview":)" << preview
          << R"(,"items":[)";
    const std::size_t limit = std::min(preview, functions.size());
    for (std::size_t i = 0; i < limit; ++i) {
        const auto& f = functions[i];
        if (i)
            *out_ << ",";
        *out_ << R"({"name":")" << Escape(f.Name()) << R"(","start":")" << std::hex << f.StartAddr()
              << R"(","end":")" << f.EndAddr() << "\"}";
    }
    *out_ << "]}\n";
}

void JsonReporter::ReportLoops(std::vector<Function>& functions, std::size_t preview) {
    *out_ << R"({"type":"loops","count":)" << functions.size() << R"(,"preview":)" << preview
          << R"(,"items":[)";
    std::size_t emitted = 0;
    for (auto& func : functions) {
        if (emitted >= preview)
            break;
        if (!func.Loops().empty()) {
            if (emitted)
                *out_ << ",";
            *out_ << R"({"name":")" << Escape(func.Name()) << R"(","loops":)"
                  << func.Loops().size() << "}";
            ++emitted;
        }
    }
    *out_ << "]}\n";
}

void JsonReporter::ReportPartition(const Partition& partition, std::size_t sample_preview) {
    (void)sample_preview;
    *out_ << R"({"type":"partition","name":")" << Escape(partition.Id()) << R"(","size":)"
          << partition.RawBytes().size() << R"(,"inputs":)" << partition.Inputs().size()
          << R"(,"outputs":)" << partition.Outputs().size() << "}\n";
}

}  // namespace splitter
