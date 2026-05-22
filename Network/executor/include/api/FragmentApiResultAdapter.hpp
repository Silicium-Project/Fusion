#pragma once

#include "api/FragmentApi.h"
#include "core/ExecutionResult.hpp"

namespace fragment::api {

bool fill_result_from_execution(const ExecutionResult& in, FE_Result* out);
void free_result_buffers(FE_Result* out);

}  // namespace fragment::api
