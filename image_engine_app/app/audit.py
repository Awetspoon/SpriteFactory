"""Audit runner (one command) for validating project readiness.

Run:
    PYTHONPATH=image_engine_app python -m app.audit --app-data-dir ./_audit

Outputs:
    audit_report.json
    audit_report.md
"""

from __future__ import annotations

import argparse
import compileall
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any

from app.paths import ensure_app_paths


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    details: dict[str, Any]
    duration_ms: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _find_project_root() -> Path:
    """Best-effort locate repo root that contains the image_engine_app folder."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "image_engine_app"
        if candidate.is_dir() and (candidate / "app" / "main.py").exists():
            # parent is .../SpriteFactory_Windows_Python_V2
            return parent
    return Path.cwd()


def _run_check(name: str, fn) -> CheckResult:
    start = time.perf_counter()
    ok = False
    details: dict[str, Any] = {}
    try:
        ok, details = fn()
    except Exception as exc:  # pragma: no cover
        ok = False
        details = {"error": f"{type(exc).__name__}: {exc}"}
    dur = int((time.perf_counter() - start) * 1000)
    return CheckResult(name=name, ok=ok, details=details, duration_ms=dur)


def _check_structure(project_root: Path) -> tuple[bool, dict[str, Any]]:
    required = [
        "image_engine_app/app/main.py",
        "image_engine_app/engine",
        "image_engine_app/ui",
        "image_engine_app/tests",
        "run_app.ps1",
        "build_exe.ps1",
        "spritefactory.spec",
        "BUILD_LOCK.md",
    ]
    missing = []
    for rel in required:
        if not (project_root / rel).exists():
            missing.append(rel)
    ok = len(missing) == 0
    return ok, {"missing": missing, "required_count": len(required)}


def _check_compileall(project_root: Path) -> tuple[bool, dict[str, Any]]:
    target = project_root / "image_engine_app"
    ok = compileall.compile_dir(str(target), quiet=1)
    return bool(ok), {"target": str(target)}


def _check_env_caps() -> tuple[bool, dict[str, Any]]:
    caps = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "has_pyside6": importlib.util.find_spec("PySide6") is not None,
        "has_pillow": importlib.util.find_spec("PIL") is not None,
        "has_pyinstaller": importlib.util.find_spec("PyInstaller") is not None,
    }
    # Always 'ok' - this check reports capability status.
    return True, caps


def _run_unittest(project_root: Path) -> tuple[bool, dict[str, Any]]:
    env = os.environ.copy()
    # Ensure the module layout matches how Marcus runs the app.
    env["PYTHONPATH"] = "image_engine_app" + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "image_engine_app/tests", "-p", "test_*.py"]
    proc = subprocess.run(cmd, cwd=str(project_root), env=env, capture_output=True, text=True)
    ok = proc.returncode == 0
    out_tail = (proc.stdout or "").strip().splitlines()[-60:]
    err_tail = (proc.stderr or "").strip().splitlines()[-60:]
    return ok, {
        "cmd": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout_tail": out_tail,
        "stderr_tail": err_tail,
    }


def _check_packaging_files(project_root: Path) -> tuple[bool, dict[str, Any]]:
    paths = {
        "onedir_spec": project_root / "spritefactory.spec",
        "onefile_spec": project_root / "spritefactory_onefile.spec",
        "runtime_hook_dir": project_root / "pyinstaller_rthooks",
        "icon": project_root / "spritefactory.ico",
        "version_info": project_root / "pyinstaller_version_info.py",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    ok = len(missing) == 0
    return ok, {"missing": missing, "paths": {k: str(p) for k, p in paths.items()}}


def _write_reports(app_data_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    json_path = app_data_dir / "audit_report.json"
    md_path = app_data_dir / "audit_report.md"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Sprite Factory Audit Report")
    lines.append("")
    lines.append(f"- Timestamp (UTC): {report.get('timestamp_utc')}")
    lines.append(f"- Project root: {report.get('project_root')}")
    lines.append(f"- Overall: **{'PASS' if report.get('overall_ok') else 'FAIL'}**")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    for chk in report.get("checks", []):
        status = "PASS" if chk.get("ok") else "FAIL"
        lines.append(f"- **{chk.get('name')}**: {status} ({chk.get('duration_ms')} ms)")
    lines.append("")
    lines.append("## Details")
    lines.append("")
    for chk in report.get("checks", []):
        lines.append(f"### {chk.get('name')}")
        lines.append("")
        lines.append(f"- Status: **{'PASS' if chk.get('ok') else 'FAIL'}**")
        lines.append(f"- Duration: {chk.get('duration_ms')} ms")
        details = chk.get("details", {})
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(details, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sprite Factory audit runner")
    parser.add_argument("--app-data-dir", default=None, help="Override app data root (writes audit_report.* here)")
    parser.add_argument("--skip-tests", action="store_true", help="Skip unit test run (faster)")
    args = parser.parse_args(argv)

    project_root = _find_project_root()
    paths = ensure_app_paths(base_dir=args.app_data_dir)
    # Use the app-data root directly (matches BUILD_LOCK spec).
    out_dir = paths.root
    out_dir.mkdir(parents=True, exist_ok=True)

    checks: list[CheckResult] = []
    checks.append(_run_check("env_caps", _check_env_caps))
    checks.append(_run_check("structure", lambda: _check_structure(project_root)))
    checks.append(_run_check("compileall", lambda: _check_compileall(project_root)))
    checks.append(_run_check("packaging_files", lambda: _check_packaging_files(project_root)))
    if not args.skip_tests:
        checks.append(_run_check("unit_tests", lambda: _run_unittest(project_root)))

    overall_ok = all(chk.ok for chk in checks if chk.name != "env_caps")

    report = {
        "timestamp_utc": _now_iso(),
        "project_root": str(project_root),
        "overall_ok": overall_ok,
        "checks": [asdict(c) for c in checks],
    }

    json_path, md_path = _write_reports(out_dir, report)
    print(f"[audit] overall_ok={overall_ok}")
    print(f"[audit] wrote: {json_path}")
    print(f"[audit] wrote: {md_path}")
    return 0 if overall_ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

