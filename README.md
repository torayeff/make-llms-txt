# make_llms_txt

Build a single LLM-friendly markdown file from Sphinx documentation.

Runs `sphinx-build` with the markdown builder, then concatenates all generated
pages in toctree order into one `llms.txt` file. Autodoc content (API
references pulled from Python docstrings) is fully resolved.

## Requirements

- Python 3.10+
- A working Sphinx build environment (Sphinx + your project's docs dependencies)
- [`sphinx-markdown-builder`](https://pypi.org/project/sphinx-markdown-builder/)

```bash
pip install sphinx-markdown-builder
```

`sphinx-markdown-builder` must also be listed in your Sphinx `conf.py` extensions:

```python
extensions = [
    # ... your other extensions ...
    "sphinx_markdown_builder",
]
```

## Usage

```bash
# From inside your docs/ directory
python /path/to/make_llms_txt.py

# Or point to the docs directory explicitly
python make_llms_txt.py /path/to/project/docs

# Custom output path
python make_llms_txt.py /path/to/project/docs -o llms.txt

# Add section numbering (useful for referencing sections in LLM prompts)
python make_llms_txt.py --numbered

# Skip sphinx-build and just re-concatenate existing markdown
python make_llms_txt.py --skip-build
```

Output is written to `<docs_dir>/_build/llms.txt` by default.

## What it does

1. Detects the root document from `conf.py` (`master_doc` / `root_doc`, defaults to `index`)
2. Parses `.. toctree::` directives recursively to discover all pages in order
3. Runs `sphinx-build -b markdown` to render `.rst` sources into `.md` (resolving all autodoc directives)
4. Strips image links (`![](...)`) and raw HTML blocks that are meaningless to LLMs
5. Concatenates everything into a single file with section separators

## What works

- Sphinx projects using **reStructuredText** (`.rst`) source files
- Nested toctrees (parsed recursively)
- `autodoc` directives (`autoclass`, `automethod`, `autofunction`, etc.)
- `literalinclude` directives (external code files are inlined)
- Projects with `master_doc` or `root_doc` set to something other than `index`

## What does NOT work

- **MyST Markdown** source files (`.md` with `` ```{toctree} `` fences) -- the toctree parser only reads `.rst` syntax
- Images and diagrams (`inheritance-diagram`, `graphviz`) -- stripped
- Interactive elements (3D model viewers, embedded HTML widgets) -- stripped

## Output format

Each page becomes a section separated by a line of `=` characters. Code blocks
retain triple-backtick fencing with language tags. With `--numbered`, each
separator includes a section index and source page name for easy reference.