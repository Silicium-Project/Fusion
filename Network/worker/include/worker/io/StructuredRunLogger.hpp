#pragma once

#include <fstream>
#include <memory>
#include <string>

namespace worker {

class StructuredRunLogger {
public:
    explicit StructuredRunLogger(std::string file_path, std::string component = "worker");

    static std::string DefaultLogPath();
    static std::string EscapeForJson(const std::string& value);
    static std::string QuoteForJson(const std::string& value);

    bool enabled() const;
    const std::string& path() const;
    const std::string& run_id() const;

    void info(const std::string& event, const std::string& message, const std::string& payload_json);
    void warning(const std::string& event, const std::string& message, const std::string& payload_json);
    void error(const std::string& event, const std::string& message, const std::string& payload_json);

private:
    static std::string GenerateRunId();
    static std::string TimestampUtcNow();
    void emit(const std::string& level,
              const std::string& event,
              const std::string& message,
              const std::string& payload_json);

    std::string path_;
    std::string component_;
    std::string run_id_;
    std::shared_ptr<std::ofstream> stream_;
};

}  // namespace worker
