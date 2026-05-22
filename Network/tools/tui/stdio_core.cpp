#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#ifndef _WIN32
#include <sys/wait.h>
#endif

namespace {

std::string json_escape(const std::string &input) {
  std::string out;
  out.reserve(input.size() + 8);
  for (char ch : input) {
    switch (ch) {
    case '\\':
      out += "\\\\";
      break;
    case '"':
      out += "\\\"";
      break;
    case '\n':
      out += "\\n";
      break;
    case '\r':
      out += "\\r";
      break;
    case '\t':
      out += "\\t";
      break;
    default:
      out.push_back(ch);
      break;
    }
  }
  return out;
}

void emit_log(const std::string &line) {
  std::cout << "{\"type\":\"log\",\"line\":\"" << json_escape(line) << "\"}" << '\n';
  std::cout.flush();
}

void emit_state(const std::string &status, int exit_code, const std::string &error = "") {
  std::cout << "{\"type\":\"state\",\"status\":\"" << status << "\",\"exit_code\":" << exit_code;
  if (!error.empty()) {
    std::cout << ",\"error\":\"" << json_escape(error) << "\"";
  }
  std::cout << "}" << '\n';
  std::cout.flush();
}

std::string extract_json_string(const std::string &payload, const std::string &key) {
  std::string pattern = "\"" + key + "\"";
  std::size_t key_pos = payload.find(pattern);
  if (key_pos == std::string::npos) {
    return "";
  }
  std::size_t colon_pos = payload.find(':', key_pos + pattern.size());
  if (colon_pos == std::string::npos) {
    return "";
  }
  std::size_t quote_start = payload.find('"', colon_pos + 1);
  if (quote_start == std::string::npos) {
    return "";
  }
  ++quote_start;
  std::string result;
  result.reserve(256);
  bool escape = false;
  for (std::size_t i = quote_start; i < payload.size(); ++i) {
    const char ch = payload[i];
    if (escape) {
      switch (ch) {
      case 'n':
        result.push_back('\n');
        break;
      case 'r':
        result.push_back('\r');
        break;
      case 't':
        result.push_back('\t');
        break;
      case '"':
      case '\\':
      case '/':
        result.push_back(ch);
        break;
      default:
        result.push_back(ch);
        break;
      }
      escape = false;
      continue;
    }
    if (ch == '\\') {
      escape = true;
      continue;
    }
    if (ch == '"') {
      return result;
    }
    result.push_back(ch);
  }
  return "";
}

int b64_value(char ch) {
  if (ch >= 'A' && ch <= 'Z') {
    return ch - 'A';
  }
  if (ch >= 'a' && ch <= 'z') {
    return ch - 'a' + 26;
  }
  if (ch >= '0' && ch <= '9') {
    return ch - '0' + 52;
  }
  if (ch == '+') {
    return 62;
  }
  if (ch == '/') {
    return 63;
  }
  return -1;
}

std::string b64_decode(const std::string &input) {
  std::string output;
  output.reserve((input.size() * 3) / 4);
  int val = 0;
  int bits = -8;
  for (char ch : input) {
    if (ch == '=') {
      break;
    }
    int decoded = b64_value(ch);
    if (decoded < 0) {
      continue;
    }
    val = (val << 6) + decoded;
    bits += 6;
    if (bits >= 0) {
      output.push_back(static_cast<char>((val >> bits) & 0xFF));
      bits -= 8;
    }
  }
  return output;
}

int normalize_exit_code(int raw_code) {
#ifdef _WIN32
  return raw_code;
#else
  if (raw_code == -1) {
    return 1;
  }
  if (WIFEXITED(raw_code)) {
    return WEXITSTATUS(raw_code);
  }
  if (WIFSIGNALED(raw_code)) {
    return 128 + WTERMSIG(raw_code);
  }
  return raw_code;
#endif
}

int close_process_pipe(FILE *pipe) {
#ifdef _WIN32
  return _pclose(pipe);
#else
  return pclose(pipe);
#endif
}

using ProcessPipe = std::unique_ptr<FILE, decltype(&close_process_pipe)>;

ProcessPipe open_process_pipe(const std::string &command_line) {
#ifdef _WIN32
  std::string wrapped = "cmd /C " + command_line + " 2>&1";
  return ProcessPipe(_popen(wrapped.c_str(), "r"), &close_process_pipe);
#else
  std::string wrapped = command_line + " 2>&1";
  return ProcessPipe(popen(wrapped.c_str(), "r"), &close_process_pipe);
#endif
}

int close_process_pipe_and_get_code(ProcessPipe &pipe) {
  if (!pipe) {
    return -1;
  }
  auto raw = pipe.release();
  return close_process_pipe(raw);
}

int run_command_and_stream(const std::string &command_line) {
  if (command_line.empty()) {
    emit_state("failed", 1, "missing command");
    return 1;
  }

  ProcessPipe pipe = open_process_pipe(command_line);
  if (!pipe) {
    emit_state("failed", 1, "unable to spawn child command");
    return 1;
  }

  char buffer[4096];
  while (std::fgets(buffer, sizeof(buffer), pipe.get()) != nullptr) {
    std::string line(buffer);
    while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) {
      line.pop_back();
    }
    emit_log(line);
  }

  int raw_code = close_process_pipe_and_get_code(pipe);
  int exit_code = normalize_exit_code(raw_code);
  emit_state(exit_code == 0 ? "completed" : "failed", exit_code);
  return exit_code;
}

} // namespace

int main() {
  std::ios::sync_with_stdio(false);
  std::cin.tie(nullptr);

  std::string payload;
  if (!std::getline(std::cin, payload)) {
    emit_state("failed", 1, "missing input payload");
    return 1;
  }

  std::string command_b64 = extract_json_string(payload, "command_b64");
  std::string command_line = b64_decode(command_b64);
  int exit_code = run_command_and_stream(command_line);
  return exit_code;
}
