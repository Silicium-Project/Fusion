#include "support/StructuredRunLogger.hpp"

#include <chrono>
#include <cstdlib>
#include <random>

namespace fragment::log {

namespace {

std::string hex_string(std::uint64_t value, std::size_t width) {
    std::ostringstream oss;
    oss << std::hex << std::setw(static_cast<int>(width)) << std::setfill('0') << value;
    return oss.str();
}

std::string compact_timestamp_utc() {
    const auto now = std::chrono::system_clock::now();
    const auto now_time = std::chrono::system_clock::to_time_t(now);
    std::tm utc_tm{};
#ifdef _WIN32
    gmtime_s(&utc_tm, &now_time);
#else
    gmtime_r(&now_time, &utc_tm);
#endif
    std::ostringstream oss;
    oss << std::put_time(&utc_tm, "%Y%m%dT%H%M%SZ");
    return oss.str();
}

}  // namespace

StructuredRunLogger::StructuredRunLogger(std::string file_path, std::string component)
    : path_(std::move(file_path)),
      component_(std::move(component)),
      run_id_(GenerateRunId()) {
    if (path_.empty())
        return;

    stream_ = std::make_shared<std::ofstream>(path_, std::ios::out | std::ios::trunc);
    if (!(*stream_))
        stream_.reset();
}

std::string StructuredRunLogger::DefaultLogPath() {
    std::random_device rd;
    std::mt19937_64 rng(rd());
    std::uniform_int_distribution<std::uint64_t> dist;
    const std::string name = "fragment_executor-" + compact_timestamp_utc()
                           + "-" + hex_string(dist(rng), 8) + ".ndjson";
    return (std::filesystem::current_path() / name).string();
}

std::string StructuredRunLogger::EscapeForJson(const std::string& value) {
    std::ostringstream oss;
    for (char c : value) {
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

std::string StructuredRunLogger::QuoteForJson(const std::string& value) {
    return "\"" + EscapeForJson(value) + "\"";
}

bool StructuredRunLogger::enabled() const {
    return static_cast<bool>(stream_);
}

const std::string& StructuredRunLogger::path() const {
    return path_;
}

const std::string& StructuredRunLogger::run_id() const {
    return run_id_;
}

std::string StructuredRunLogger::TimestampUtcNow() {
    using namespace std::chrono;
    const auto now = system_clock::now();
    const auto sec = time_point_cast<seconds>(now);
    const auto millis = duration_cast<milliseconds>(now - sec).count();
    const auto now_time = system_clock::to_time_t(now);
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

std::string StructuredRunLogger::GenerateRunId() {
    if (const char* env_run_id = std::getenv("EXECUTOR_RUN_ID"); env_run_id && *env_run_id)
        return env_run_id;
    if (const char* env_run_id = std::getenv("SILICIUM_RUN_ID"); env_run_id && *env_run_id)
        return env_run_id;

    std::random_device rd;
    std::mt19937_64 rng(rd());
    std::uniform_int_distribution<std::uint64_t> dist;
    return "executor-" + hex_string(dist(rng), 16);
}

void StructuredRunLogger::emit(const std::string& level,
                               const std::string& event,
                               const std::string& message,
                               const std::string& payload_json) {
    if (!enabled())
        return;

    (*stream_) << R"({"schema_version":1,"timestamp":)" << QuoteForJson(TimestampUtcNow())
               << R"(,"component":)" << QuoteForJson(component_)
               << R"(,"level":)" << QuoteForJson(level)
               << R"(,"run_id":)" << QuoteForJson(run_id_)
               << R"(,"event":)" << QuoteForJson(event)
               << R"(,"message":)" << QuoteForJson(message)
               << R"(,"payload":)" << payload_json << "}\n";
    stream_->flush();
}

void StructuredRunLogger::info(const std::string& event,
                               const std::string& message,
                               const std::string& payload_json) {
    emit("info", event, message, payload_json);
}

void StructuredRunLogger::warning(const std::string& event,
                                  const std::string& message,
                                  const std::string& payload_json) {
    emit("warn", event, message, payload_json);
}

void StructuredRunLogger::error(const std::string& event,
                                const std::string& message,
                                const std::string& payload_json) {
    emit("error", event, message, payload_json);
}

}  // namespace fragment::log
