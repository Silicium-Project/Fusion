#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Structures POD pour échanges C.
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
    const char* summary_path;    // chemin vers summary.json
    const char* partition_id;    // identifiant de partition à exécuter
    const char* binary_path;     // chemin absolu du binaire original (optionnel)
    const FE_RegisterKV* inputs; // entrées explicites (overrides)
    size_t input_count;
    const FE_RegisterKV* register_state;  // état de registre préexistant (LUT)
    size_t register_state_count;
    const FE_MemoryPage* memory_pages;    // pages mémoire à précharger
    size_t memory_page_count;
    const FE_FdRedirection* fd_redirections;  // FDs supplémentaires
    size_t fd_redirections_count;
    int native_mode;   // 0 = ému, 1 = natif
    int force_native;  // 0 = garde-fous, 1 = ignore garde-fous
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
    const char* error_message;
    uint64_t instructions_executed;
    uint64_t memory_accesses;
    FE_ChangedRegister* changed_registers;
    size_t changed_registers_count;
    FE_MemoryPatchOut* memory_patches;
    size_t memory_patches_count;
    char* program_stdout;
    char* program_stderr;
    FE_FdOutput* fd_outputs;
    size_t fd_outputs_count;
} FE_Result;

typedef struct FE_Context FE_Context;

// Création/destruction d’un contexte d’exécution.
FE_Context* fe_create(void);
void fe_destroy(FE_Context* ctx);

// Exécute une tâche; retourne 0 en cas de succès (appel), renseigne FE_Result.
int fe_run(FE_Context* ctx, const FE_Task* task, FE_Result* out);

// Libère les buffers alloués dans FE_Result.
void fe_free_result(FE_Result* out);

#ifdef __cplusplus
}
#endif
