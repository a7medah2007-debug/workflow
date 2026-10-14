"""Custom pytest hooks for py-md-docs."""

import pytest
import typing

if typing.TYPE_CHECKING:
    from markdown_it import MarkdownIt


def pytest_py_md_docs_globals() -> typing.Dict[str, typing.Any]:
    """Hook to inject global variables into tested code blocks."""
    return {}


@pytest.hookspec(firstresult=True)
def pytest_py_md_docs_markdown_it() -> "MarkdownIt":
    """Configure a custom markdown_it.MarkdownIt parser."""
    from markdown_it import MarkdownIt

    return MarkdownIt()


# Backwards compatibility hooks for pytest-markdown-docs hooks
def pytest_markdown_docs_globals() -> typing.Dict[str, typing.Any]:
    """Compatibility hook to inject global variables."""
    return {}


@pytest.hookspec(firstresult=True)
def pytest_markdown_docs_markdown_it() -> "MarkdownIt":
    """Compatibility hook to configure custom markdown_it parser."""
    from markdown_it import MarkdownIt

    return MarkdownIt()
