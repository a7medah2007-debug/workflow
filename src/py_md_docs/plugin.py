"""Pytest plugin implementation for py-md-docs."""

import inspect
import logging
import pathlib
import types
import typing
from enum import Enum

import pytest
from _pytest._code import ExceptionInfo
from _pytest.config.argparsing import Parser
from _pytest.pathlib import import_path

from py_md_docs import hooks
from py_md_docs._runners import get_runner
from py_md_docs.definitions import FenceTestDefinition, ObjectTestDefinition

if pytest.version_tuple >= (8, 0, 0):
    from _pytest.fixtures import TopRequest
else:
    from _pytest.fixtures import FixtureRequest as TopRequest  # type: ignore

if typing.TYPE_CHECKING:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token

logger = logging.getLogger("py-md-docs")

MARKER_NAMES = ("py-md-docs", "markdown-docs")


class FenceSyntax(Enum):
    default = "default"
    superfences = "superfences"


def get_docstring_start_line(obj: typing.Any) -> typing.Optional[int]:
    """Find the line number where an object's docstring begins."""
    try:
        source_lines, start_line = inspect.getsourcelines(obj)
    except OSError:
        return None

    for idx, line in enumerate(source_lines):
        stripped = line.strip()
        if stripped.startswith(('"""', "'''")):
            return start_line + idx

    return None


def _get_asyncio_runner(fixture_request: TopRequest):
    """Attempt to acquire pytest-asyncio event loop runner."""
    try:
        return fixture_request.getfixturevalue("_function_scoped_runner")
    except Exception:
        return None


def _preprocess_async_fixtures_if_available(collector: pytest.Collector) -> None:
    """Preprocess async fixtures if pytest-asyncio is installed."""
    try:
        from pytest_asyncio.plugin import _preprocess_async_fixtures, _HOLDER  # type: ignore

        _preprocess_async_fixtures(collector, _HOLDER)
    except ImportError:
        pass


class MarkdownInlinePythonItem(pytest.Item):
    """Pytest test item for an individual Python markdown fence block."""

    def __init__(
        self,
        name: str,
        parent: typing.Union["MarkdownDocstringCodeModule", "MarkdownTextFile"],
        test_definition: FenceTestDefinition,
    ) -> None:
        super().__init__(name, parent)
        for marker in MARKER_NAMES:
            self.add_marker(marker)
        self.code = test_definition.source
        self.obj = None
        self.test_definition = test_definition
        self.user_properties.append(("code", test_definition.source))
        self.start_line = test_definition.start_line
        self.fixturenames = list(test_definition.fixture_names)
        self.nofuncargs = True
        self.runner_name = test_definition.runner_name

    def setup(self):
        def _dummy() -> None:
            pass

        self.funcargs = {}
        self._fixtureinfo = self.session._fixturemanager.getfixtureinfo(
            node=self, func=_dummy, cls=None
        )
        self.fixture_request = TopRequest(self, _ispytest=True)
        self.fixture_request._fillfixtures()
        self.runner = get_runner(self.runner_name)

    def runtest(self):
        # Fetch globals from both py_md_docs and backwards-compatible hooks
        global_sets = []
        if hasattr(self.parent.config.hook, "pytest_py_md_docs_globals"):
            global_sets.extend(self.parent.config.hook.pytest_py_md_docs_globals())
        if hasattr(self.parent.config.hook, "pytest_markdown_docs_globals"):
            global_sets.extend(self.parent.config.hook.pytest_markdown_docs_globals())

        mod = types.ModuleType("py_md_docs_fence")
        all_globals = mod.__dict__
        for global_set in global_sets:
            if isinstance(global_set, dict):
                all_globals.update(global_set)

        # Evaluate fixtures requested by the snippet
        for fixture_name in self._fixtureinfo.names_closure:
            self.fixture_request.getfixturevalue(fixture_name)

        for argname, value in self.funcargs.items():
            all_globals[argname] = value

        max_retries = self.test_definition.max_retries
        max_attempts = max_retries + 1

        last_exception = None
        for attempt in range(max_attempts):
            try:
                capman = self.config.pluginmanager.getplugin("capturemanager")
                asyncio_runner = _get_asyncio_runner(self.fixture_request)
                if capman:
                    with capman.global_and_fixture_disabled():
                        try:
                            self.runner.runtest(
                                self.test_definition,
                                all_globals,
                                asyncio_runner=asyncio_runner,
                            )
                        except TypeError:
                            self.runner.runtest(self.test_definition, all_globals)
                else:
                    self.runner.runtest(self.test_definition, all_globals)

                if attempt > 0:
                    self.user_properties.append(("retries", str(attempt)))
                return
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    continue
                raise

        if last_exception:
            raise last_exception

    def repr_failure(
        self,
        excinfo: ExceptionInfo[BaseException],
        style=None,
    ) -> str:
        return self.runner.repr_failure(self.test_definition, excinfo, style)

    def reportinfo(self):
        return self.path, self.start_line, self.name


def get_prefixed_strings(
    seq: typing.Collection[str], prefix: str
) -> typing.Sequence[str]:
    return tuple(s[len(prefix) :] for s in seq if s.startswith(prefix))


def parse_superfences_block_info(block_info: str) -> typing.List[str]:
    block_info = block_info.strip()
    if not block_info.startswith("{"):
        return block_info.split()

    block_info = block_info.strip("{}")
    code_info = block_info.split()
    dot_lang = next((p for p in code_info if p.startswith(".")), None)
    if dot_lang:
        code_info.remove(dot_lang)
        lang = dot_lang[1:]
        code_info.insert(0, lang)
    return code_info


def is_mdx_comment(block: "Token") -> bool:
    return (
        block.type == "inline"
        and block.content.strip().startswith("{/*")
        and block.content.strip().endswith("*/}")
        and "pmd-metadata:" in block.content
    )


def extract_options_from_mdx_comment(comment: str) -> typing.Set[str]:
    comment = (
        comment.strip()
        .replace("{/*", "")
        .replace("*/}", "")
        .replace("pmd-metadata:", "")
    )
    return set(option.strip() for option in comment.split(" ") if option)


def extract_fence_tests(
    markdown_it_parser: "MarkdownIt",
    markdown_string: str,
    start_line_offset: int,
    source_path: pathlib.Path,
    markdown_type: str = "md",
    fence_syntax: FenceSyntax = FenceSyntax.default,
) -> typing.Generator[FenceTestDefinition, None, None]:
    tokens = markdown_it_parser.parse(markdown_string)

    prev = ""
    for i, block in enumerate(tokens):
        if block.type != "fence" or not block.map:
            continue

        if fence_syntax == FenceSyntax.superfences:
            code_info = parse_superfences_block_info(block.info)
        else:
            code_info = block.info.split()

        lang = code_info[0] if code_info else None
        code_options = set(code_info) - {lang}

        if markdown_type == "mdx" and i >= 2 and is_mdx_comment(tokens[i - 2]):
            code_options |= extract_options_from_mdx_comment(tokens[i - 2].content)

        if lang in ("py", "python", "python3") and "notest" not in code_options:
            start_line = start_line_offset + block.map[0] + 1
            if "continuation" not in code_options:
                prev = ""

            add_blank_lines = max(0, start_line - prev.count("\n"))
            code_block = prev + ("\n" * add_blank_lines) + block.content

            fixture_names = get_prefixed_strings(code_options, "fixture:")
            runner_names = get_prefixed_strings(code_options, "runner:")
            runner_name = runner_names[0] if runner_names else None

            retry_counts = get_prefixed_strings(code_options, "retry:")
            max_retries = 0
            if retry_counts:
                try:
                    max_retries = max(0, int(retry_counts[0]))
                except ValueError as e:
                    raise ValueError(f"Invalid retry count '{retry_counts[0]}'") from e

            yield FenceTestDefinition(
                source=code_block,
                fixture_names=fixture_names,
                start_line=start_line,
                source_path=source_path,
                runner_name=runner_name,
                max_retries=max_retries,
            )
            prev = code_block


class MarkdownDocstringCodeModule(pytest.Module):
    """Pytest module collector for Python docstrings."""

    def collect(self):
        _preprocess_async_fixtures_if_available(self)

        if pytest.version_tuple >= (8, 1, 0):
            module = import_path(
                self.path, root=self.config.rootpath, consider_namespace_packages=True
            )
        else:
            module = import_path(self.path, root=self.config.rootpath)

        for object_test in self.find_object_tests_recursive(
            module.__name__, module, set(), set()
        ):
            fence_test = object_test.fence_test
            yield MarkdownInlinePythonItem.from_parent(
                self,
                name=f"{object_test.object_name}[Fence#{object_test.intra_object_index + 1}][line:{fence_test.start_line}]",
                test_definition=fence_test,
            )

    def find_object_tests_recursive(
        self,
        module_name: str,
        obj: typing.Any,
        visited_objects: typing.Set[int],
        found_tests: typing.Set[typing.Tuple[str, int]],
    ) -> typing.Generator[ObjectTestDefinition, None, None]:
        if id(obj) in visited_objects:
            return
        visited_objects.add(id(obj))

        docstr = inspect.getdoc(obj)

        for _, member in inspect.getmembers(obj):
            if (
                inspect.isclass(member)
                or inspect.isfunction(member)
                or inspect.ismethod(member)
            ) and getattr(member, "__module__", None) == module_name:
                yield from self.find_object_tests_recursive(
                    module_name, member, visited_objects, found_tests
                )

        if docstr:
            docstring_offset = get_docstring_start_line(obj)
            if docstring_offset is not None:
                obj_name = (
                    getattr(obj, "__qualname__", None)
                    or getattr(obj, "__name__", None)
                    or "<Unnamed>"
                )
                fence_syntax = FenceSyntax(
                    getattr(self.config.option, "markdowndocs_syntax", "default")
                )
                parser = self._get_markdown_parser()

                for i, fence_test in enumerate(
                    extract_fence_tests(
                        parser,
                        docstr,
                        docstring_offset,
                        source_path=self.path,
                        fence_syntax=fence_syntax,
                    )
                ):
                    found_test = ObjectTestDefinition(i, obj_name, fence_test)
                    loc = (module_name, fence_test.start_line)
                    if loc not in found_tests:
                        found_tests.add(loc)
                        yield found_test

    def _get_markdown_parser(self) -> "MarkdownIt":
        if hasattr(self.config.hook, "pytest_py_md_docs_markdown_it"):
            res = self.config.hook.pytest_py_md_docs_markdown_it()
            if res:
                return res
        if hasattr(self.config.hook, "pytest_markdown_docs_markdown_it"):
            res = self.config.hook.pytest_markdown_docs_markdown_it()
            if res:
                return res
        from markdown_it import MarkdownIt

        return MarkdownIt(config="commonmark")


class MarkdownTextFile(pytest.File):
    """Pytest file collector for markdown files (.md, .mdx, .svx)."""

    def collect(self):
        _preprocess_async_fixtures_if_available(self)

        markdown_content = self.path.read_text("utf8")
        fence_syntax = FenceSyntax(
            getattr(self.config.option, "markdowndocs_syntax", "default")
        )
        parser = self._get_markdown_parser()

        for i, fence_test in enumerate(
            extract_fence_tests(
                parser,
                markdown_content,
                source_path=self.path,
                start_line_offset=0,
                markdown_type=self.path.suffix.replace(".", ""),
                fence_syntax=fence_syntax,
            )
        ):
            yield MarkdownInlinePythonItem.from_parent(
                self,
                name=f"[Fence#{i + 1}][line:{fence_test.start_line}]",
                test_definition=fence_test,
            )

    def _get_markdown_parser(self) -> "MarkdownIt":
        if hasattr(self.config.hook, "pytest_py_md_docs_markdown_it"):
            res = self.config.hook.pytest_py_md_docs_markdown_it()
            if res:
                return res
        if hasattr(self.config.hook, "pytest_markdown_docs_markdown_it"):
            res = self.config.hook.pytest_markdown_docs_markdown_it()
            if res:
                return res
        from markdown_it import MarkdownIt

        return MarkdownIt(config="commonmark")


def pytest_collect_file(file_path, parent):
    is_enabled = getattr(parent.config.option, "markdowndocs", False) or getattr(
        parent.config.option, "py_md_docs", False
    )

    if is_enabled:
        pathlib_path = pathlib.Path(str(file_path))
        if pathlib_path.suffix == ".py":
            return MarkdownDocstringCodeModule.from_parent(parent, path=pathlib_path)
        elif pathlib_path.suffix in (".md", ".mdx", ".svx"):
            return MarkdownTextFile.from_parent(parent, path=pathlib_path)

    return None


def pytest_configure(config):
    for marker in MARKER_NAMES:
        config.addinivalue_line(
            "markers", f"{marker}: filter for tests generated by py-md-docs"
        )


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("collect")
    group.addoption(
        "--py-md-docs",
        "--markdown-docs",
        action="store_true",
        default=False,
        help="Run Python markdown code blocks as pytest tests",
        dest="py_md_docs",
    )
    group.addoption(
        "--markdown-docs-syntax",
        action="store",
        choices=[choice.value for choice in FenceSyntax],
        default="default",
        help="Choose markdown code fence syntax (default or superfences)",
        dest="markdowndocs_syntax",
    )


def pytest_addhooks(pluginmanager):
    pluginmanager.add_hookspecs(hooks)


@pytest.hookimpl
def pytest_py_md_docs_markdown_it() -> "MarkdownIt":
    from markdown_it import MarkdownIt

    return MarkdownIt(config="commonmark")
