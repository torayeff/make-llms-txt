#!/usr/bin/env python3
"""Build a single LLM-friendly markdown file from Sphinx documentation.

Runs sphinx-build with the markdown builder, then concatenates all generated
.md files in toctree order into a single llms.txt file.

The toctree structure is parsed dynamically from the .rst source files,
so new pages are picked up automatically.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)\s*\n?")
RAW_HTML_BLOCK_RE = re.compile(
    r"<(script|model-viewer|style)[^>]*>.*?</\1>\s*\n?", re.DOTALL
)

TOCTREE_DIRECTIVE_RE = re.compile(r"^\.\.\s+toctree::", re.MULTILINE)
TOCTREE_OPTION_RE = re.compile(r"^\s+:[^:]+:.*$")


def detect_master_doc(docs_dir: Path) -> str:
    """Read conf.py and return the master_doc setting (default: 'index')."""
    conf_path = docs_dir / "conf.py"
    if not conf_path.exists():
        return "index"

    try:
        tree = ast.parse(conf_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return "index"

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ("master_doc", "root_doc")
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value

    return "index"


def parse_toctree_entries(rst_path: Path) -> list[str]:
    """Extract all toctree entries from an .rst file, in order."""
    if not rst_path.exists():
        return []

    text = rst_path.read_text(encoding="utf-8")
    entries: list[str] = []

    for match in TOCTREE_DIRECTIVE_RE.finditer(text):
        block_start = match.end()
        lines = text[block_start:].split("\n")

        in_options = True
        for line in lines:
            stripped = line.strip()

            if in_options:
                if not stripped or TOCTREE_OPTION_RE.match(line):
                    continue
                in_options = False

            if not stripped:
                break

            if stripped.startswith(":") or stripped.startswith(".."):
                continue

            entry = stripped.removesuffix(".rst")
            entries.append(entry)

    return entries


def collect_pages(
    docs_dir: Path,
    start: str = "index",
    *,
    _visited: set[str] | None = None,
) -> list[str]:
    """Recursively walk toctrees starting from a root page, returning ordered pages."""
    if _visited is None:
        _visited = set()

    if start in _visited:
        return []
    _visited.add(start)

    pages: list[str] = [start]

    rst_path = docs_dir / f"{start}.rst"
    if not rst_path.exists() and "/" not in start:
        rst_path = docs_dir / start / "index.rst"

    for child in parse_toctree_entries(rst_path):
        if "/" not in child and not (docs_dir / f"{child}.rst").exists():
            child_in_parent = f"{Path(start).parent / child}"
            if (docs_dir / f"{child_in_parent}.rst").exists():
                child = child_in_parent
        pages.extend(collect_pages(docs_dir, child, _visited=_visited))

    return pages


def clean_markdown(text: str) -> str:
    """Remove image links and raw HTML blocks that are useless for LLMs."""
    text = IMAGE_LINK_RE.sub("", text)
    text = RAW_HTML_BLOCK_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def run_sphinx_build(docs_dir: Path, build_dir: Path) -> bool:
    """Run sphinx-build with the markdown builder."""
    print(f"Building markdown docs into {build_dir} ...")
    result = subprocess.run(
        [
            sys.executable, "-m", "sphinx",
            "-b", "markdown",
            str(docs_dir),
            str(build_dir),
        ],
        cwd=docs_dir,
    )
    if result.returncode != 0:
        print("sphinx-build failed.", file=sys.stderr)
        return False
    return True


def concatenate(
    build_dir: Path,
    pages: list[str],
    *,
    numbered: bool = False,
) -> str:
    """Read and concatenate markdown files in order."""
    parts: list[str] = []
    missing: list[str] = []

    for i, page in enumerate(pages):
        md_path = build_dir / f"{page}.md"
        if not md_path.exists():
            missing.append(page)
            continue

        content = clean_markdown(md_path.read_text(encoding="utf-8"))
        if not content:
            continue

        separator = "=" * 72
        if numbered:
            header = f"{separator}\nSection {i}: {page}\n{separator}"
        else:
            header = separator

        parts.append(f"{header}\n\n{content}")

    if missing:
        print(f"Warning: missing pages: {', '.join(missing)}", file=sys.stderr)

    return "\n\n\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a single LLM-friendly file from Sphinx docs.",
    )
    parser.add_argument(
        "docs_dir",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Path to the Sphinx docs source directory (default: current dir)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output file path (default: <docs_dir>/_build/llms.txt)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip the sphinx-build step (use existing _build/markdown)",
    )
    parser.add_argument(
        "--numbered",
        action="store_true",
        help="Add section numbering to the output",
    )
    args = parser.parse_args()

    docs_dir = args.docs_dir.resolve()
    build_dir = docs_dir / "_build" / "markdown"
    output = args.output or (docs_dir / "_build" / "llms.txt")

    if not (docs_dir / "conf.py").exists():
        print(f"Error: no conf.py found in {docs_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.skip_build:
        if not run_sphinx_build(docs_dir, build_dir):
            sys.exit(1)

    master_doc = detect_master_doc(docs_dir)
    pages = collect_pages(docs_dir, master_doc)
    print(f"Discovered {len(pages)} pages from toctree (root: {master_doc})")

    result = concatenate(build_dir, pages, numbered=args.numbered)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")

    size_kb = output.stat().st_size / 1024
    print(f"Wrote {output} ({size_kb:.0f} KB, {len(pages)} sections)")


if __name__ == "__main__":
    main()
