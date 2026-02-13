#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// POD structures for C API exchanges.
typedef struct {
    const char* name;
    uint64_t value;
} FE_RegisterKV;

typedef struct {
    uint64_t address;
    const uint8_t* data;
    size_t size;
} FE_MemoryPage;

typedef struct {
    int fd;
    const uint8_t* input_data;
    size_t input_size;
    int capture;  // bool
    const char* alias;
} FE_FdRedirection;

typedef struct {
    const char* summary_path;    // path to summary.json
    const char* partition_id;    // partition identifier to execute
    const char* binary_path;     // absolute path of original binary (optional)
    const FE_RegisterKV* inputs; // explicit register overrides
    size_t input_count;
    const FE_RegisterKV* register_state;  // pre-existing register state
    size_t register_state_count;
    const FE_MemoryPage* memory_pages;    // memory pages to preload
    size_t memory_page_count;
    const FE_FdRedirection* fd_redirections;  // extra FD redirections
    size_t fd_redirections_count;
    int native_mode;   // 0 = emu, 1 = native
    int force_native;  // 0 = safeguards enabled, 1 = ignore safeguards
} FE_Task;

typedef struct {
    const char* name;
    uint64_t before;
    uint64_t after;
} FE_ChangedRegister;

typedef struct {
    uint64_t address;
    uint8_t* before;
    size_t before_size;
    uint8_t* after;
    size_t after_size;
} FE_MemoryPatchOut;

typedef struct {
    int fd;
    uint8_t* data;
    size_t size;
    char* alias;
} FE_FdOutput;

typedef struct {
    int success;
    const char* error_message;  // callee-owned (release with fe_free_result)
    uint64_t instructions_executed;
    uint64_t memory_accesses;
    FE_ChangedRegister* changed_registers;  // callee-owned
    size_t changed_registers_count;
    FE_MemoryPatchOut* memory_patches;  // callee-owned
    size_t memory_patches_count;
    char* program_stdout;  // callee-owned
    char* program_stderr;  // callee-owned
    FE_FdOutput* fd_outputs;  // callee-owned
    size_t fd_outputs_count;
} FE_Result;

typedef struct FE_Context FE_Context;

// Create/destroy execution context.
FE_Context* fe_create(void);
void fe_destroy(FE_Context* ctx);

// Executes one task and writes FE_Result on success.
// Returns:
//   0  = success
//  -1  = invalid arguments
//  -2  = invalid summary
//  -3  = partition not found
//  -4  = backend execution failure
//  -5  = ABI result conversion failure
//
// Ownership:
// - FE_Task pointers are always caller-owned.
// - FE_Result buffers are always callee-owned until fe_free_result.
int fe_run(FE_Context* ctx, const FE_Task* task, FE_Result* out);

// Releases all callee-owned FE_Result buffers and zeroes the structure.
void fe_free_result(FE_Result* out);

#ifdef __cplusplus
}
#endif
