from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from tools.codingstyle.core import load_rules_from_json


def _load_rule(tmp_path: Path, *, allowlist: list[dict[str, str]] | None = None):
    payload = {
        "id": "cpp.interface_contract_naming",
        "kind": "cpp_interface_contract_naming",
        "severity": "error",
        "sanitize": "cpp",
        "scope": {"include": ["**/*.hpp"]},
        "allowlist": allowlist or [],
    }
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps(payload), encoding="utf-8")
    return load_rules_from_json(rules_file)[0]


def test_interface_contract_requires_i_prefix_and_virtual_destructor(tmp_path: Path) -> None:
    rule = _load_rule(tmp_path)
    source = """
class Contract {
public:
    virtual void run() = 0;
};
"""
    issues = rule.check(PurePosixPath("module/include/contract.hpp"), tmp_path / "contract.hpp", source)
    messages = [issue.message for issue in issues]
    assert any("must use 'I*' prefix" in msg for msg in messages)
    assert any("must declare a virtual or pure virtual destructor" in msg for msg in messages)


def test_allowlisted_non_i_interface_keeps_destructor_enforcement(tmp_path: Path) -> None:
    rule = _load_rule(
        tmp_path,
        allowlist=[{"path": "module/include/contract.hpp", "name": "Contract"}],
    )
    source = """
class Contract {
public:
    virtual void run() = 0;
};
"""
    issues = rule.check(PurePosixPath("module/include/contract.hpp"), tmp_path / "contract.hpp", source)
    messages = [issue.message for issue in issues]
    assert not any("must use 'I*' prefix" in msg for msg in messages)
    assert any("must declare a virtual or pure virtual destructor" in msg for msg in messages)


def test_i_prefix_interface_with_virtual_destructor_passes(tmp_path: Path) -> None:
    rule = _load_rule(tmp_path)
    source = """
class IContract {
public:
    virtual ~IContract() = default;
    virtual void run() = 0;
};
"""
    issues = rule.check(PurePosixPath("module/include/contract.hpp"), tmp_path / "contract.hpp", source)
    assert issues == []


def test_override_destructor_is_accepted_for_derived_abstract_contract(tmp_path: Path) -> None:
    rule = _load_rule(tmp_path)
    source = """
class IBase {
public:
    virtual ~IBase() = default;
    virtual void run() = 0;
};

class IDerived : public IBase {
public:
    ~IDerived() override = default;
    virtual void run_more() = 0;
};
"""
    issues = rule.check(PurePosixPath("module/include/contract.hpp"), tmp_path / "contract.hpp", source)
    assert issues == []
