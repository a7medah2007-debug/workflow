# Py-MD-Docs (py-md-docs)

> **Author:** Ahmed Hassan  
> **License:** MIT License  

A powerful [pytest](https://docs.pytest.org) plugin that discovers and executes Python code snippets from Markdown files and inline Python docstrings as standard unit tests.

---

## Features

- **Markdown Files:** Automatically tests Python fences (```` ```python ````, ```` ```py ````, ```` ```python3 ````) in `.md`, `.mdx`, and `.svx` files.
- **Docstring Tests:** Discovers and executes code snippets inside class, function, and method docstrings.
- **Fixtures Integration:** Full support for pytest fixtures (`autouse` and named fixtures using `fixture:<name>`).
- **Async Fixtures Support:** Works seamlessly with `pytest-asyncio` fixtures and top-level await expressions.
- **Stateful Continuation:** Chain multiple snippets with `continuation` to preserve variables across fences.
- **Flaky Test Retries:** Automatically retry unreliable or network-dependent tests with `retry:N`.
- **Custom Markdown Parser:** Customize markdown parsing plugins (e.g. `mkdocs` admonitions) via hooks.
- **Material for MkDocs:** Support for `pymdownx.superfences` curly-brace syntax (`--markdown-docs-syntax=superfences`).
- **MDX Comments:** Support for MDX metadata comments (`{/* pmd-metadata: ... */}`).

---

## Installation

```bash
pip install py-md-docs
```

Or for development / editable mode:

```bash
pip install -e .
```

---

## Quick Start

### 1. Markdown Files

In any markdown file (`README.md`, `docs/index.md`):

````markdown
# Welcome to My Library

```python
name = "World"
assert f"Hello, {name}!" == "Hello, World!"
```
````

Run pytest with the `--py-md-docs` flag:

```bash
pytest --py-md-docs
```

*(You can also use the drop-in alias `--markdown-docs`)*.

---

### 2. Python Docstrings

In your Python code:

````python
class Calculator:
    def add(self, a: int, b: int) -> int:
        """Add two numbers together.

        Example:
        ```python
        from mymodule import Calculator
        calc = Calculator()
        assert calc.add(2, 3) == 5
        ```
        """
        return a + b
````

---

## Advanced Usage

### Skipping Tests

Exclude a code block from being tested by adding `notest`:

````markdown
```python notest
# This block will not be run as a test
raise RuntimeError("Skipped!")
```
````

### Fixtures

Inject pytest fixtures using `fixture:<name>`:

````markdown
```python fixture:tmp_path fixture:capsys
test_file = tmp_path / "hello.txt"
test_file.write_text("Hello from file!")
print(test_file.read_text())

captured = capsys.readouterr()
assert "Hello from file!" in captured.out
```
````

### Continuation (Carry Over State)

Carry variables and imports from one block to the next using `continuation`:

````markdown
```python
x = 10
y = 20
```

```python continuation
assert x + y == 30
```
````

### Automatic Retries

Retry transient or network-dependent tests up to `N` times with `retry:N`:

````markdown
```python retry:3
import random
# Will retry up to 3 times (4 attempts total)
assert random.choice([True, False, True])
```
````

### Injecting Global Variables

Define custom globals in your `conftest.py`:

```python
# conftest.py
def pytest_py_md_docs_globals():
    import math
    return {"math": math, "APP_ENV": "test"}
```

Then use them in snippets without manual imports:

````markdown
```python
assert math.sqrt(16) == 4
assert APP_ENV == "test"
```
````

---

## License

This project is licensed under the **MIT License**.  
Copyright (c) 2026 **Ahmed Hassan**. See the [LICENSE](LICENSE) file for details.
