"""Unit tests for py-md-docs core functionality."""

import pathlib
import pytest
from markdown_it import MarkdownIt

from py_md_docs.plugin import (
    extract_fence_tests,
    FenceSyntax,
    parse_superfences_block_info,
    extract_options_from_mdx_comment,
)
from py_md_docs._runners import get_runner
from py_md_docs.definitions import FenceTestDefinition


def test_extract_basic_code_blocks():
    parser = MarkdownIt()
    md = """# Hello

```python
x = 1
assert x == 1
```

```javascript
console.log("ignore me");
```

```py
y = 2
assert y == 2
```
"""
    tests = list(
        extract_fence_tests(
            parser,
            md,
            start_line_offset=0,
            source_path=pathlib.Path("test.md"),
        )
    )
    assert len(tests) == 2
    assert "assert x == 1" in tests[0].source
    assert "assert y == 2" in tests[1].source


def test_notest_skipping():
    parser = MarkdownIt()
    md = """
```python notest
raise RuntimeError("Should be skipped")
```
"""
    tests = list(
        extract_fence_tests(
            parser,
            md,
            start_line_offset=0,
            source_path=pathlib.Path("test.md"),
        )
    )
    assert len(tests) == 0


def test_fixtures_and_retry_parsing():
    parser = MarkdownIt()
    md = """
```python fixture:capsys fixture:tmp_path retry:3
print("hello")
```
"""
    tests = list(
        extract_fence_tests(
            parser,
            md,
            start_line_offset=0,
            source_path=pathlib.Path("test.md"),
        )
    )
    assert len(tests) == 1
    assert "capsys" in tests[0].fixture_names
    assert "tmp_path" in tests[0].fixture_names
    assert tests[0].max_retries == 3


def test_continuation_preserves_state():
    parser = MarkdownIt()
    md = """
```python
a = 10
```

```python continuation
b = 20
assert a + b == 30
```
"""
    tests = list(
        extract_fence_tests(
            parser,
            md,
            start_line_offset=0,
            source_path=pathlib.Path("test.md"),
        )
    )
    assert len(tests) == 2
    assert "a = 10" in tests[1].source
    assert "b = 20" in tests[1].source


def test_superfences_syntax():
    parsed = parse_superfences_block_info("{.python continuation fixture:capsys}")
    assert parsed[0] == "python"
    assert "continuation" in parsed
    assert "fixture:capsys" in parsed


def test_mdx_comment_metadata():
    options = extract_options_from_mdx_comment("{/* pmd-metadata: notest fixture:capsys */}")
    assert "notest" in options
    assert "fixture:capsys" in options


def test_default_runner_execution():
    runner = get_runner(None)
    defn = FenceTestDefinition(
        source="res = 40 + 2\nassert res == 42",
        fixture_names=(),
        start_line=1,
        source_path=pathlib.Path("example.md"),
    )
    globals_dict = {}
    runner.runtest(defn, globals_dict)
    assert globals_dict["res"] == 42


def test_default_runner_failure():
    runner = get_runner(None)
    defn = FenceTestDefinition(
        source="assert 1 == 2",
        fixture_names=(),
        start_line=1,
        source_path=pathlib.Path("example.md"),
    )
    with pytest.raises(AssertionError):
        runner.runtest(defn, {})
