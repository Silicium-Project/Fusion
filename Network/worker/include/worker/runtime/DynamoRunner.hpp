#pragma once

#include <string>
#include <vector>

namespace worker {

class DynamoRunner {
public:
    explicit DynamoRunner(std::string launcher_path = std::string());

    bool run_binary(const std::string& binary_path,
                    const std::vector<std::string>& args,
                    std::string& stdout_buffer,
                    std::string& stderr_buffer) const;

private:
    std::string launcher_path_;
};

}  // namespace worker
