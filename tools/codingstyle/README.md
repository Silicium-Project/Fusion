# Coding Style Rules

This folder contains JSON-driven rules used by the coding style checker.

## Usage
- List rules: `python tools/style_check.py --list-rules`
- Run all rules: `python tools/style_check.py`
- Treat warnings as errors: `python tools/style_check.py --warnings-as-errors`
- Run a subset: `python tools/style_check.py --rules cpp.single_namespace_class --rules cpp.pragma_once_header`

## Rules
- `cpp.single_namespace_class`: Allow at most one namespace and one class/struct definition per file.
- `cpp.no_using_namespace_header`: Disallow `using namespace` directives in headers.
- `cpp.pragma_once_header`: Require exactly one `#pragma once` in headers.
- `cpp.primary_class_filename`: Primary class/struct name should match the file name.
- `cpp.header_source_pair`: Headers under include/ should have a matching source under src/.
- `cpp.include_order`: Order includes with `<system/third-party>` before `"project"`.
- `cpp.no_unsafe_allocation`: Disallow `new`/`delete`, C allocation APIs, and raw pointer declarations.
- `py.file_snake_case`: Python file names should be snake_case.
- `py.function_snake_case`: Python function names should be snake_case.
- `py.final_constant_upper_snake`: `Final`-annotated constants should be UPPER_SNAKE_CASE.
