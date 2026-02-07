#pragma once

#include "core/Common.hpp"

namespace fragment::log {

void banner();

void section(std::string_view title);

void subsection(std::string_view title);

void info(std::string_view message);

void warning(std::string_view message);

void error(std::string_view message);

}  // namespace fragment::log
