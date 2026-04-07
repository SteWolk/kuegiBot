from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALL_SCAN_ROOTS = ("kuegi_bot", "backtest.py", "cryptobot.py")
SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    ".assistant_workspace",
    "__pycache__",
    "ta-lib-python",
    "backtest",  # local-only and ignored by project policy
}


@dataclass
class Issue:
    file: Path
    line: int
    code: str
    message: str

    def render(self) -> str:
        rel = self.file.relative_to(ROOT).as_posix()
        return f"{rel}:{self.line}: {self.code} {self.message}"


def _run_git_changed_files() -> List[Path]:
    cmd = ["git", "-C", str(ROOT), "status", "--porcelain"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return []

    files: List[Path] = []
    for raw_line in proc.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        path_text = line[3:]
        if " -> " in path_text:
            path_text = path_text.split(" -> ", maxsplit=1)[1]
        path = ROOT / path_text
        if path.suffix == ".py" and path.exists():
            files.append(path.resolve())
    # keep deterministic order and remove duplicates
    return sorted(set(files))


def _iter_python_files(paths: Sequence[str]) -> Iterable[Path]:
    for entry in paths:
        path = (ROOT / entry).resolve()
        if not path.exists():
            continue
        if path.is_file() and path.suffix == ".py":
            yield path
            continue
        if not path.is_dir():
            continue
        for file in path.rglob("*.py"):
            if any(skip in file.parts for skip in SKIP_DIR_NAMES):
                continue
            yield file.resolve()


def _complexity(node: ast.AST) -> int:
    points = 1
    complexity_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.AsyncWith,
        ast.IfExp,
        ast.ExceptHandler,
        ast.BoolOp,
        ast.Match,
    )
    for item in ast.walk(node):
        if isinstance(item, complexity_nodes):
            points += 1
    return points


def _duplicate_import_issues(tree: ast.AST, file: Path) -> List[Issue]:
    issues: List[Issue] = []
    seen = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                key = ("import", name.name, name.asname)
                if key in seen:
                    issues.append(Issue(file=file, line=node.lineno, code="Q003", message=f"duplicate import '{name.name}'"))
                seen.add(key)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for name in node.names:
                key = ("from", module, node.level, name.name, name.asname)
                if key in seen:
                    issues.append(
                        Issue(
                            file=file,
                            line=node.lineno,
                            code="Q003",
                            message=f"duplicate from-import '{module}:{name.name}'",
                        )
                    )
                seen.add(key)
    return issues


def _semicolon_statement_lines(text: str) -> set[int]:
    lines = set()
    for tok in tokenize.generate_tokens(iter(text.splitlines(keepends=True)).__next__):
        token_type = tok.type
        token_string = tok.string
        if token_type == tokenize.OP and token_string == ";":
            lines.add(tok.start[0])
    return lines


def _scan_file(file: Path, max_line_length: int, max_complexity: int, check_semicolons: bool) -> List[Issue]:
    issues: List[Issue] = []
    text = file.read_text(encoding="utf-8")
    lines = text.splitlines()
    semicolon_lines = _semicolon_statement_lines(text) if check_semicolons else set()

    for idx, line in enumerate(lines, start=1):
        if max_line_length > 0 and len(line) > max_line_length:
            issues.append(
                Issue(
                    file=file,
                    line=idx,
                    code="Q001",
                    message=f"line too long ({len(line)} > {max_line_length})",
                )
            )
        if idx in semicolon_lines:
            issues.append(Issue(file=file, line=idx, code="Q002", message="multiple statements on one line (';')"))

    try:
        tree = ast.parse(text, filename=str(file))
    except SyntaxError as exc:
        line_no = exc.lineno or 1
        issues.append(Issue(file=file, line=line_no, code="Q000", message=f"syntax error: {exc.msg}"))
        return issues

    issues.extend(_duplicate_import_issues(tree, file))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            score = _complexity(node)
            if max_complexity > 0 and score > max_complexity:
                issues.append(
                    Issue(
                        file=file,
                        line=node.lineno,
                        code="Q004",
                        message=f"function '{node.name}' complexity {score} exceeds {max_complexity}",
                    )
                )

    return issues


def _collect_targets(scope: str, include: Sequence[str]) -> List[Path]:
    include_paths = list(include)
    if include_paths:
        return sorted(set(_iter_python_files(include_paths)))

    if scope == "changed":
        changed = _run_git_changed_files()
        if changed:
            return changed

    return sorted(set(_iter_python_files(DEFAULT_ALL_SCAN_ROOTS)))


def run_quality_gate(
    scope: str,
    include: Sequence[str],
    max_line_length: int,
    max_complexity: int,
    check_semicolons: bool,
) -> int:
    targets = _collect_targets(scope=scope, include=include)
    if not targets:
        print("QUALITY_GATE: no python files matched")
        return 0

    all_issues: List[Issue] = []
    for file in targets:
        all_issues.extend(
            _scan_file(
                file=file,
                max_line_length=max_line_length,
                max_complexity=max_complexity,
                check_semicolons=check_semicolons,
            )
        )

    if all_issues:
        print(f"QUALITY_GATE: FAIL ({len(all_issues)} issues across {len(targets)} files)")
        for issue in all_issues:
            print(issue.render())
        return 1

    print(f"QUALITY_GATE: PASS ({len(targets)} files)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Repository-native Python quality gate.")
    parser.add_argument("--scope", choices=("changed", "all"), default="changed")
    parser.add_argument("--include", action="append", default=[], help="Optional path(s) relative to repository root.")
    parser.add_argument("--max-line-length", type=int, default=0, help="0 disables line-length check.")
    parser.add_argument("--max-complexity", type=int, default=80, help="0 disables complexity check.")
    parser.add_argument("--check-semicolons", action="store_true", help="Fail on semicolon statement separators.")
    args = parser.parse_args()
    return run_quality_gate(
        scope=args.scope,
        include=args.include,
        max_line_length=args.max_line_length,
        max_complexity=args.max_complexity,
        check_semicolons=args.check_semicolons,
    )


if __name__ == "__main__":
    raise SystemExit(main())
