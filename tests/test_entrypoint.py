import logging
import re
from pathlib import Path
from typing import Any, Callable

import pytest


logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)
TEST_DATA_PATH = Path(__file__).with_name("testdata.txt")
PLACEHOLDER_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _load_test_scenarios() -> list[dict[str, Any]]:
    raw_scenarios, variables = _parse_spec_file(TEST_DATA_PATH)
    scenarios = []
    for scenario in raw_scenarios:
        resolved = _resolve_placeholders(scenario, variables)
        resolved["command"] = _build_command(resolved["operation"])
        scenarios.append(resolved)
    LOGGER.info(
        "Loaded %s test scenarios (variables=%s)",
        len(scenarios),
        len(variables),
    )
    return scenarios


def _resolve_placeholders(value: Any, variables: dict) -> Any:
    if isinstance(value, str):
        return PLACEHOLDER_PATTERN.sub(
            lambda match: _lookup_variable(match.group(1), variables), value
        )
    if isinstance(value, list):
        return [_resolve_placeholders(item, variables) for item in value]
    if isinstance(value, dict):
        return {
            key: _resolve_placeholders(val, variables)
            for key, val in value.items()
        }
    return value


def _lookup_variable(path: str, variables: dict) -> str:
    if path not in variables:
        raise KeyError(f"Unknown variable '{path}'")
    return str(variables[path])


def _parse_spec_file(path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    scenarios: list[dict[str, Any]] = []
    variables: dict[str, str] = {}
    current: dict | None = None

    for line_no, raw_line in enumerate(path.read_text().splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        keyword, remainder = _split_keyword(stripped)

        if keyword == "var":
            key, value = _split_required(
                remainder, path, line_no, "var <key> <value>"
            )
            variables[key] = value
            continue

        if keyword == "scenario":
            if current:
                _finalize_scenario(current, scenarios, path, line_no)
            scenario_id = remainder.strip()
            if not scenario_id:
                raise ValueError(f"{path}:{line_no} scenario id missing")
            current = {
                "id": scenario_id,
                "description": "",
                "operation": None,
                "rules": [],
                "extra_env": {},
            }
            continue

        if keyword == "end":
            if not current:
                raise ValueError(f"{path}:{line_no} 'end' without scenario")
            _finalize_scenario(current, scenarios, path, line_no)
            current = None
            continue

        if not current:
            raise ValueError(
                f"{path}:{line_no} Keyword '{keyword}' outside scenario"
            )

        if keyword == "desc":
            current["description"] = remainder.strip()
            continue

        if keyword == "env":
            key, value = _split_required(
                remainder, path, line_no, "env <KEY> <value>"
            )
            current["extra_env"][key] = value
            continue

        if keyword == "op":
            current["operation"] = _parse_operation(
                remainder, path, line_no
            )
            continue

        if keyword == "rule":
            current["rules"].append(
                _parse_rule(remainder, path, line_no)
            )
            continue

        raise ValueError(f"{path}:{line_no} Unknown keyword '{keyword}'")

    if current:
        _finalize_scenario(current, scenarios, path, line_no=None)

    return scenarios, variables


def _split_keyword(line: str) -> tuple[str, str]:
    parts = line.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _split_required(
    text: str, path: Path, line_no: int | None, expectation: str
) -> tuple[str, str]:
    parts = text.split(None, 1)
    if len(parts) != 2:
        location = f"{path}:{line_no}" if line_no else str(path)
        raise ValueError(f"{location} Expected '{expectation}'")
    return parts[0], parts[1]


def _finalize_scenario(
    scenario: dict, scenarios: list[dict], path: Path, line_no: int | None
) -> None:
    if not scenario.get("operation"):
        location = f"{path}:{line_no}" if line_no else str(path)
        raise ValueError(f"{location} Scenario '{scenario['id']}' missing op")
    if not scenario["extra_env"]:
        scenario.pop("extra_env")
    scenarios.append(scenario)


def _parse_operation(remainder: str, path: Path, line_no: int) -> dict:
    tokens = remainder.split()
    if not tokens:
        raise ValueError(f"{path}:{line_no} op requires arguments")
    op_type = tokens[0]
    args = tokens[1:]
    if op_type == "start_network":
        op = {"type": "start_network"}
        if args:
            op["network"] = args[0]
            if len(args) > 1:
                op["extra_args"] = args[1:]
        return op
    if op_type == "cli_command":
        program = args[0] if args else "solana"
        op = {"type": "cli_command", "program": program}
        if len(args) > 1:
            op["args"] = args[1:]
        return op
    if op_type == "airdrop":
        if len(args) < 2:
            raise ValueError(
                f"{path}:{line_no} airdrop requires <amount> <destination>"
            )
        op = {
            "type": "airdrop",
            "amount": args[0],
            "destination": args[1],
        }
        if len(args) > 2:
            op["flags"] = args[2:]
        return op
    if op_type == "transfer":
        if len(args) < 2:
            raise ValueError(
                f"{path}:{line_no} transfer requires <destination> <amount>"
            )
        op = {
            "type": "transfer",
            "destination": args[0],
            "amount": args[1],
        }
        if len(args) > 2:
            op["flags"] = args[2:]
        return op
    raise ValueError(f"{path}:{line_no} Unknown op '{op_type}'")


def _parse_rule(remainder: str, path: Path, line_no: int) -> dict:
    if not remainder:
        raise ValueError(f"{path}:{line_no} rule requires arguments")
    name, rest = _split_keyword(remainder)
    if name in {"expect_success", "expect_failure"}:
        return {"rule": name}
    if name == "stderr_contains":
        if not rest:
            raise ValueError(
                f"{path}:{line_no} stderr_contains requires substring"
            )
        return {"rule": name, "substring": rest}
    if name == "log_contains":
        log_name, snippet = _split_required(
            rest, path, line_no, "rule log_contains <log> <snippet>"
        )
        return {"rule": name, "log": log_name, "snippet": snippet}
    if name == "log_requires_entries":
        if not rest:
            raise ValueError(
                f"{path}:{line_no} log_requires_entries needs log name"
            )
        return {"rule": name, "log": rest}
    if name == "file_exists":
        if not rest:
            raise ValueError(
                f"{path}:{line_no} file_exists requires a relative path"
            )
        return {"rule": name, "relative_path": rest}
    raise ValueError(f"{path}:{line_no} Unknown rule '{name}'")


def _build_command(operation: dict[str, Any]) -> list[str]:
    op_type = operation["type"]
    builder = OPERATION_BUILDERS.get(op_type)
    assert builder, f"Unknown operation type '{op_type}'"
    command = builder(operation)
    LOGGER.info(
        "Constructed command for operation '%s': %s",
        op_type,
        command,
    )
    return command


def _op_start_network(operation: dict[str, Any]) -> list[str]:
    cmd = ["silicium-node", "start"]
    network = operation.get("network")
    if network:
        cmd.extend(["--network", network])
    cmd.extend(operation.get("extra_args", []))
    return cmd


def _op_cli_command(operation: dict[str, Any]) -> list[str]:
    program = operation.get("program", "solana")
    args = operation.get("args", [])
    return [program, *args]


def _op_airdrop(operation: dict[str, Any]) -> list[str]:
    amount = str(operation["amount"])
    destination = operation["destination"]
    cmd = ["solana", "airdrop", amount, destination]
    cmd.extend(operation.get("flags", []))
    return cmd


def _op_transfer(operation: dict[str, Any]) -> list[str]:
    amount = str(operation["amount"])
    destination = operation["destination"]
    cmd = ["solana", "transfer", destination, amount]
    cmd.extend(operation.get("flags", []))
    return cmd


OperationBuilder = Callable[[dict[str, Any]], list[str]]

OPERATION_BUILDERS: dict[str, OperationBuilder] = {
    "start_network": _op_start_network,
    "cli_command": _op_cli_command,
    "airdrop": _op_airdrop,
    "transfer": _op_transfer,
}


TEST_SCENARIOS = _load_test_scenarios()


def _get_log_lines(case, log_name: str, context: dict) -> list[str]:
    cache = context.setdefault("logs", {})
    if log_name not in cache:
        cache[log_name] = case.read_log(log_name)
        LOGGER.info(
            "[%s] Loaded %d lines from log '%s'",
            context["scenario"]["id"],
            len(cache[log_name]),
            log_name,
        )
    return cache[log_name]


def _rule_expect_success(rule_spec: dict, context: dict) -> None:
    case = context["case"]
    assert (
        case.result.returncode == 0
    ), f"[{context['scenario']['id']}] Expected success, got: {case.result.stderr}"


def _rule_expect_failure(rule_spec: dict, context: dict) -> None:
    case = context["case"]
    assert (
        case.result.returncode != 0
    ), f"[{context['scenario']['id']}] Expected failure but command succeeded"


def _rule_stderr_contains(rule_spec: dict, context: dict) -> None:
    substring = rule_spec["substring"]
    case = context["case"]
    assert (
        substring in case.result.stderr
    ), f"[{context['scenario']['id']}] Missing stderr fragment '{substring}'"


def _rule_log_contains(rule_spec: dict, context: dict) -> None:
    log_name = rule_spec["log"]
    snippet = rule_spec["snippet"]
    lines = _get_log_lines(context["case"], log_name, context)
    assert any(
        snippet in line for line in lines
    ), f"[{context['scenario']['id']}] '{snippet}' missing in '{log_name}' log: {lines}"


def _rule_log_requires_entries(rule_spec: dict, context: dict) -> None:
    log_name = rule_spec["log"]
    lines = _get_log_lines(context["case"], log_name, context)
    assert lines, f"[{context['scenario']['id']}] Expected '{log_name}' to produce output"


def _rule_file_exists(rule_spec: dict, context: dict) -> None:
    relative = rule_spec["relative_path"]
    target = context["case"].home / relative
    assert (
        target.exists()
    ), f"[{context['scenario']['id']}] Expected file to exist: {target}"


RULE_HANDLERS = {
    "expect_success": _rule_expect_success,
    "expect_failure": _rule_expect_failure,
    "stderr_contains": _rule_stderr_contains,
    "log_contains": _rule_log_contains,
    "log_requires_entries": _rule_log_requires_entries,
    "file_exists": _rule_file_exists,
}


@pytest.mark.parametrize(
    "scenario",
    TEST_SCENARIOS,
    ids=lambda scenario: scenario["id"],
)
def test_entrypoint_runs_declared_rules(entrypoint_runner, scenario):
    LOGGER.info(
        "[%s] Running command=%s extra_env=%s",
        scenario["id"],
        scenario["command"],
        scenario.get("extra_env"),
    )
    case = entrypoint_runner(
        scenario["command"], extra_env=scenario.get("extra_env")
    )
    LOGGER.info(
        "[%s] Return code=%s stderr=%s",
        scenario["id"],
        case.result.returncode,
        case.result.stderr.strip(),
    )
    context = {"scenario": scenario, "case": case, "logs": {}}
    for rule_spec in scenario.get("rules", []):
        rule_name = rule_spec["rule"]
        handler = RULE_HANDLERS.get(rule_name)
        assert handler, f"Unknown rule '{rule_name}'"
        LOGGER.info(
            "[%s] Applying rule '%s' with params %s",
            scenario["id"],
            rule_name,
            {k: v for k, v in rule_spec.items() if k != "rule"},
        )
        handler(rule_spec, context)
