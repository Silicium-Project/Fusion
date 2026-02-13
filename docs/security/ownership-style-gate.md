# C++ Ownership Safety Gate

This project enforces an ownership safety gate with the style checker rule:
- `cpp.no_unsafe_allocation`

The rule blocks:
- raw `new` / `delete`
- C allocation APIs (`malloc`, `calloc`, `realloc`, `free`)
- raw pointer declarations that usually imply ambiguous ownership

## CI Gate

In CI (`.github/workflows/tests.yml`), the gate runs on changed files only:

```bash
python tools/style_check.py \
  --rules cpp.no_unsafe_allocation \
  --changed-against "$BASE_SHA" \
  --changed-head "$HEAD_SHA"
```

This prevents new unsafe ownership patterns while allowing incremental cleanup of legacy code.

## Local Command

Run the same gate locally before pushing:

```bash
python tools/style_check.py --rules cpp.no_unsafe_allocation --changed-against origin/main --changed-head HEAD
```

You can also target specific files:

```bash
python tools/style_check.py --rules cpp.no_unsafe_allocation --path worker/src/foo.cpp --path worker/include/foo.hpp
```

## False Positives and Suppression Policy

1. **First choice: refactor** to safe ownership (`std::unique_ptr`, `std::shared_ptr`, references, containers, RAII wrappers).
2. If a violation is intentional and required (interop boundary, ABI/C API shim), document why in the code review and open a follow-up cleanup issue.
3. Use **narrow scope suppression only** via rule scope exclusion in `tools/codingstyle/rules/cpp_no_unsafe_allocation.json` (file-level, not broad globs).
4. Every suppression must include:
   - exact file path
   - rationale
   - follow-up issue link for removal

There is intentionally no blanket global suppression and no silent ignore policy.
