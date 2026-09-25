import argparse
from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET

from .config import SCENARIOS, Settings, template
from .core import Fixture, builtin_fixture, run_case
from .reference import ReferenceAdapter


def _adapter(spec):
    module, factory = spec.split(":", 1)
    adapter = getattr(importlib.import_module(module), factory)()
    if not all(callable(getattr(adapter, name, None)) for name in ("command", "snapshot")):
        raise ValueError("adapter must provide command and snapshot")
    for module_name in getattr(adapter, "required_modules", ()):
        if importlib.util.find_spec(module_name) is None:
            raise ValueError(f"missing optional module: {module_name}")
    return adapter


def _exit_code(reports):
    statuses = {report["status"] for report in reports}
    if "error" in statuses:
        return 2
    if "fail" in statuses:
        return 1
    return 3 if "unsupported" in statuses else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bounded connector pagination and recovery checks")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--config", type=Path, default=Path("cursorcheck.toml"))
    init.add_argument("--dlt", action="store_true")
    for name in ("demo", "run", "replay", "doctor"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path)
        command.add_argument("--output", type=Path)
        command.add_argument("--timeout", type=float)
        command.add_argument("--max-requests", type=int)
        command.add_argument("--adapter", help="trusted importable module:factory")
        if name in ("run", "doctor"):
            command.add_argument("--scenario", choices=SCENARIOS, action="append")
        elif name == "replay":
            command.add_argument("fixture", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            with args.config.open("x", encoding="utf-8") as stream:
                stream.write(template(args.dlt))
            print(f"Created {args.config}. Edit adapter to use your own trusted worker.")
            return 0
        settings = Settings.load(args.config) if args.config else Settings()
        if args.config:
            sys.path.insert(0, str(args.config.resolve().parent))
        updates = {field: value for field, value in {
            "adapter": args.adapter, "output": args.output, "timeout": args.timeout,
            "max_requests": args.max_requests}.items() if value is not None}
        if getattr(args, "scenario", None):
            updates["scenarios"] = tuple(args.scenario)
        settings = replace(settings, **updates)
        settings.validate()
        if args.command == "demo":
            print("Synthetic demo: the defective connector intentionally stops on an empty page.")
            reports = []
            for defective in (False, True):
                report = run_case(builtin_fixture("empty-middle-page"), ReferenceAdapter(defective),
                                  settings.output, timeout=settings.timeout, max_requests=settings.max_requests)
                reports.append(report)
                _show("Seeded defect" if defective else "Reference", report)
            return 0 if [report["status"] for report in reports] == ["pass", "fail"] else 2
        adapter = _adapter(settings.adapter)
        if args.command == "doctor":
            unsupported = False
            for name in settings.scenarios:
                supported = ((name != "restart-between-pages" or getattr(adapter, "restart_supported", False)) and
                             (name != "equal-cursor-boundary" or getattr(adapter, "incremental_supported", False)))
                print(f"{name}: {'SUPPORTED' if supported else 'UNSUPPORTED'}")
                unsupported |= not supported
            print("Capability check only; no worker or sync was run.")
            return 3 if unsupported else 0
        if args.command == "replay":
            report = run_case(Fixture.load(args.fixture), adapter, settings.output,
                              timeout=settings.timeout, max_requests=settings.max_requests)
            _show(settings.adapter, report)
            return _exit_code([report])
        suite_dir = settings.output.resolve() / ("suite-" + uuid.uuid4().hex)
        reports = []
        for name in settings.scenarios:
            report = run_case(builtin_fixture(name), _adapter(settings.adapter), suite_dir,
                              timeout=settings.timeout, max_requests=settings.max_requests)
            reports.append(report)
            _show(name, report)
        (suite_dir / "suite.json").write_text(json.dumps({"schema_version": 1, "cases": reports}, indent=2), encoding="utf-8")
        root = ET.Element("testsuites")
        for report in reports:
            root.append(ET.parse(Path(report["run_dir"]) / "junit.xml").getroot())
        ET.ElementTree(root).write(suite_dir / "suite.xml", encoding="utf-8", xml_declaration=True)
        print("Suite:", suite_dir)
        return _exit_code(reports)
    except (ValueError, OSError, ImportError, AttributeError, TypeError) as exc:
        print(f"Configuration error ({type(exc).__name__}); check fixture, adapter and output path.")
        return 2


def _show(label: str, report: dict) -> None:
    print(f"{label}: {report['status'].upper()} - {report['message']}")
    if report["missing"]:
        print("Missing id/version:", report["missing"][:10])
    print("Artifacts:", report["run_dir"])
