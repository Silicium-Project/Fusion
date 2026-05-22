#include "pipeline/JsonReporter.hpp"

#include <chrono>
#include <iomanip>
#include <random>
#include <sstream>

#include "support/Env.hpp"

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

std::string HexString(std::uint64_t value, std::size_t width) {
    std::ostringstream oss;
    oss << std::hex << std::setw(static_cast<int>(width)) << std::setfill('0') << value;
    return oss.str();
}

std::string JsonQuoted(const std::string& value) {
    return "\"" + Escape(value) + "\"";
}

}  // namespace

namespace {

std::shared_ptr<std::ostream> StdOutPtr() {
    return std::shared_ptr<std::ostream>(&std::cout, [](std::ostream*) {});
}

}  // namespace

JsonReporter::JsonReporter(std::shared_ptr<std::ostream> out, Mode mode)
    : out_(out ? std::move(out) : StdOutPtr()),
      mode_(mode),
      run_id_(GenerateRunId()) {}

bool JsonReporter::IsStructuredMode() const {
    return mode_ == Mode::StructuredV1Ndjson;
}

std::string JsonReporter::TimestampUtcNow() {
    using namespace std::chrono;
    const auto now = system_clock::now();
    const auto sec = time_point_cast<seconds>(now);
    const auto millis = duration_cast<milliseconds>(now - sec).count();
    const std::time_t now_time = system_clock::to_time_t(now);
    std::tm utc_tm{};
#ifdef _WIN32
    gmtime_s(&utc_tm, &now_time);
#else
    gmtime_r(&now_time, &utc_tm);
#endif
    std::ostringstream oss;
    oss << std::put_time(&utc_tm, "%Y-%m-%dT%H:%M:%S")
        << '.' << std::setw(3) << std::setfill('0') << millis
        << 'Z';
    return oss.str();
}

std::string JsonReporter::GenerateRunId() {
    if (auto env = GetEnv("SPLITTER_RUN_ID"))
        return *env;
    std::random_device rd;
    std::mt19937_64 rng(rd());
    std::uniform_int_distribution<std::uint64_t> dist;
    return "splitter-" + HexString(dist(rng), 16);
}

std::string JsonReporter::StringArray(const std::vector<std::string>& values) const {
    std::ostringstream oss;
    oss << "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i)
            oss << ",";
        oss << JsonQuoted(values[i]);
    }
    oss << "]";
    return oss.str();
}

void JsonReporter::WriteStructuredEvent(const std::string& level,
                                        const std::string& event,
                                        const std::string& message,
                                        const std::string& payload_json) {
    *out_ << R"({"schema_version":1,"timestamp":)" << JsonQuoted(TimestampUtcNow())
          << R"(,"component":"splitter","level":)" << JsonQuoted(level)
          << R"(,"run_id":)" << JsonQuoted(run_id_)
          << R"(,"event":)" << JsonQuoted(event)
          << R"(,"message":)" << JsonQuoted(message)
          << R"(,"payload":)" << payload_json << "}\n";
}

void JsonReporter::Banner(const std::string& title) {
    if (IsStructuredMode()) {
        WriteStructuredEvent("info", "banner", title, "{}");
        return;
    }
    *out_ << R"({"type":"banner","title":")" << Escape(title) << "\"}\n";
}

void JsonReporter::Info(const std::string& message) {
    if (IsStructuredMode()) {
        WriteStructuredEvent("info", "info", message, "{}");
        return;
    }
    *out_ << R"({"type":"info","message":")" << Escape(message) << "\"}\n";
}

void JsonReporter::ReportTiming(const std::string& phase, long long milliseconds) {
    if (IsStructuredMode()) {
        std::ostringstream payload;
        payload << R"({"phase":)" << JsonQuoted(phase)
                << R"(,"duration_ms":)" << milliseconds << "}";
        WriteStructuredEvent("info", "phase_timing", "Phase timing collected", payload.str());
        return;
    }
    *out_ << R"({"type":"timing","phase":")" << Escape(phase) << R"(","ms":)" << milliseconds << "}\n";
}

void JsonReporter::ReportRunStart(const std::string& binary_path, const std::string& output_dir) {
    if (!IsStructuredMode())
        return;
    std::ostringstream payload;
    payload << R"({"binary_path":)" << JsonQuoted(binary_path)
            << R"(,"output_dir":)" << JsonQuoted(output_dir) << "}";
    WriteStructuredEvent("info", "run_started", "Splitter run started", payload.str());
}

void JsonReporter::ReportRunCompleted(int exit_code, long long duration_ms) {
    if (!IsStructuredMode())
        return;
    std::ostringstream payload;
    payload << R"({"exit_code":)" << exit_code
            << R"(,"duration_ms":)" << duration_ms << "}";
    const bool ok = exit_code == 0;
    WriteStructuredEvent(ok ? "info" : "error",
                         "run_completed",
                         ok ? "Splitter run completed" : "Splitter run failed",
                         payload.str());
}

void JsonReporter::ReportPhaseStart(const std::string& phase,
                                    const std::vector<std::string>& input_artifacts,
                                    const std::vector<std::string>& output_artifacts) {
    if (!IsStructuredMode())
        return;
    std::ostringstream payload;
    payload << R"({"phase":)" << JsonQuoted(phase)
            << R"(,"input_artifacts":)" << StringArray(input_artifacts)
            << R"(,"output_artifacts":)" << StringArray(output_artifacts) << "}";
    WriteStructuredEvent("info", "phase_started", "Phase started", payload.str());
}

void JsonReporter::ReportPhaseCompleted(const std::string& phase,
                                        const std::vector<std::string>& input_artifacts,
                                        const std::vector<std::string>& output_artifacts,
                                        long long duration_ms) {
    if (!IsStructuredMode())
        return;
    std::ostringstream payload;
    payload << R"({"phase":)" << JsonQuoted(phase)
            << R"(,"input_artifacts":)" << StringArray(input_artifacts)
            << R"(,"output_artifacts":)" << StringArray(output_artifacts)
            << R"(,"duration_ms":)" << duration_ms << "}";
    WriteStructuredEvent("info", "phase_completed", "Phase completed", payload.str());
}

void JsonReporter::ReportPhaseFailed(const std::string& phase,
                                     const std::vector<std::string>& input_artifacts,
                                     const std::vector<std::string>& output_artifacts,
                                     long long duration_ms,
                                     const std::string& error_message,
                                     int error_code) {
    if (!IsStructuredMode())
        return;
    std::ostringstream payload;
    payload << R"({"phase":)" << JsonQuoted(phase)
            << R"(,"input_artifacts":)" << StringArray(input_artifacts)
            << R"(,"output_artifacts":)" << StringArray(output_artifacts)
            << R"(,"duration_ms":)" << duration_ms
            << R"(,"error":)" << JsonQuoted(error_message);
    if (error_code >= 0)
        payload << R"(,"error_code":)" << error_code;
    payload << "}";
    WriteStructuredEvent("error", "phase_failed", "Phase failed", payload.str());
}

void JsonReporter::ReportFunctions(const std::vector<Function>& functions, std::size_t preview) {
    std::ostringstream items;
    items << "[";
    const std::size_t limit = std::min(preview, functions.size());
    for (std::size_t i = 0; i < limit; ++i) {
        const auto& f = functions[i];
        if (i)
            items << ",";
        items << R"({"name":")" << Escape(f.Name()) << R"(","start":"0x)" << std::hex << f.StartAddr()
              << R"(","end":"0x)" << f.EndAddr() << "\"}";
    }
    items << "]";
    if (IsStructuredMode()) {
        std::ostringstream payload;
        payload << R"({"count":)" << functions.size()
                << R"(,"preview":)" << preview
                << R"(,"items":)" << items.str() << "}";
        WriteStructuredEvent("info", "functions_reported", "Function overview reported", payload.str());
        return;
    }
    *out_ << R"({"type":"functions","count":)" << functions.size() << R"(,"preview":)" << preview
          << R"(,"items":)" << items.str() << "}\n";
}

void JsonReporter::ReportLoops(std::vector<Function>& functions, std::size_t preview) {
    std::ostringstream items;
    items << "[";
    std::size_t emitted = 0;
    for (auto& func : functions) {
        if (emitted >= preview)
            break;
        if (!func.Loops().empty()) {
            if (emitted)
                items << ",";
            items << R"({"name":")" << Escape(func.Name()) << R"(","loops":)"
                  << func.Loops().size() << "}";
            ++emitted;
        }
    }
    items << "]";
    if (IsStructuredMode()) {
        std::ostringstream payload;
        payload << R"({"count":)" << functions.size()
                << R"(,"preview":)" << preview
                << R"(,"items":)" << items.str() << "}";
        WriteStructuredEvent("info", "loops_reported", "Loop overview reported", payload.str());
        return;
    }
    *out_ << R"({"type":"loops","count":)" << functions.size() << R"(,"preview":)" << preview
          << R"(,"items":)" << items.str() << "}\n";
}

void JsonReporter::ReportPartition(const Partition& partition, std::size_t sample_preview) {
    (void)sample_preview;
    if (IsStructuredMode()) {
        std::ostringstream payload;
        payload << R"({"partition":)" << JsonQuoted(partition.Id())
                << R"(,"size":)" << partition.RawBytes().size()
                << R"(,"inputs":)" << partition.Inputs().size()
                << R"(,"outputs":)" << partition.Outputs().size() << "}";
        WriteStructuredEvent("info", "partition_reported", "Partition reported", payload.str());
        return;
    }
    *out_ << R"({"type":"partition","name":")" << Escape(partition.Id()) << R"(","size":)"
          << partition.RawBytes().size() << R"(,"inputs":)" << partition.Inputs().size()
          << R"(,"outputs":)" << partition.Outputs().size() << "}\n";
}

}  // namespace splitter
