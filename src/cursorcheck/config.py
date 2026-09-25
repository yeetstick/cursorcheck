"""Strict, versioned configuration; relative paths belong to the config file."""

from dataclasses import dataclass
import math
from pathlib import Path
import tomllib

SCENARIOS = ("all-pages", "empty-middle-page", "equal-cursor-boundary", "retryable-page", "restart-between-pages")


@dataclass(frozen=True)
class Settings:
    adapter: str = "cursorcheck.reference:build_adapter"
    scenarios: tuple[str, ...] = SCENARIOS
    timeout: float = 30
    max_requests: int = 100
    output: Path = Path(".cursorcheck/runs")

    def validate(self):
        if not isinstance(self.adapter, str) or self.adapter.count(":") != 1 or not all(self.adapter.split(":")):
            raise ValueError("adapter must be module:factory")
        if not self.scenarios or any(name not in SCENARIOS for name in self.scenarios) or len(set(self.scenarios)) != len(self.scenarios):
            raise ValueError("scenarios must be unique supported names")
        if type(self.timeout) not in (float, int) or not math.isfinite(self.timeout) or not 0.1 <= self.timeout <= 300:
            raise ValueError("case_timeout_seconds must be between 0.1 and 300")
        if type(self.max_requests) is not int or not 1 <= self.max_requests <= 1000:
            raise ValueError("max_requests must be between 1 and 1000")

    @classmethod
    def load(cls, path: Path):
        if path.stat().st_size > 100_000:
            raise ValueError("config exceeds 100 KB")
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        if set(data) - {"schema_version", "adapter", "scenarios", "limits", "output"}:
            raise ValueError("unknown configuration fields")
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError("unsupported config schema")
        limits = data.get("limits", {})
        if not isinstance(limits, dict) or set(limits) - {"case_timeout_seconds", "max_requests"}:
            raise ValueError("unknown limits")
        scenarios = data.get("scenarios", list(SCENARIOS))
        if not isinstance(scenarios, list) or any(not isinstance(s, str) for s in scenarios):
            raise ValueError("scenarios must be an array of names")
        output = data.get("output", ".cursorcheck/runs")
        if not isinstance(output, str) or not output:
            raise ValueError("output must be a nonempty path")
        settings = cls(data.get("adapter", cls.adapter), tuple(scenarios),
                       limits.get("case_timeout_seconds", 30), limits.get("max_requests", 100),
                       (path.resolve().parent / output).resolve())
        settings.validate()
        return settings


def template(dlt: bool = False) -> str:
    adapter = "cursorcheck.dlt_adapter:build_adapter" if dlt else "cursorcheck.reference:build_adapter"
    return f'''schema_version = 1
adapter = "{adapter}"
scenarios = ["all-pages", "empty-middle-page", "equal-cursor-boundary", "retryable-page", "restart-between-pages"]
output = ".cursorcheck/runs"

[limits]
case_timeout_seconds = 30
max_requests = 100
'''
