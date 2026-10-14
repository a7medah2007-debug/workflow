"""Code runners and failure representations for py-md-docs."""

import abc
import ast
import inspect
import traceback
import typing
from abc import abstractmethod

import pytest

from py_md_docs.definitions import FenceTestDefinition

_default_runner: typing.Optional["_Runner"] = None
_registered_runners: typing.Dict[str, "_Runner"] = {}


class _Runner(metaclass=abc.ABCMeta):
    @abstractmethod
    def runtest(
        self,
        test: FenceTestDefinition,
        args: typing.Dict[str, typing.Any],
        *,
        asyncio_runner=None,
    ) -> None:
        """Execute the code snippet."""
        ...

    @abstractmethod
    def repr_failure(
        self,
        test: FenceTestDefinition,
        excinfo: pytest.ExceptionInfo[BaseException],
        style=None,
    ) -> str:
        """Format the test failure with code excerpt and traceback."""
        ...


RUNNER_TYPE = typing.TypeVar("RUNNER_TYPE", bound=typing.Type[_Runner])


def register_runner(*, default: bool = False):
    """Decorator for adding custom test runners."""

    def decorator(r: RUNNER_TYPE) -> RUNNER_TYPE:
        global _default_runner
        runner = r()
        _registered_runners[r.__name__] = runner
        if default:
            _default_runner = runner
        return r

    return decorator


@register_runner(default=True)
class DefaultRunner(_Runner):
    """Default code runner with async/await and detailed traceback support."""

    def runtest(
        self,
        test: FenceTestDefinition,
        args: typing.Dict[str, typing.Any],
        *,
        asyncio_runner=None,
    ) -> None:
        try:
            compiled = compile(
                test.source,
                filename=str(test.source_path),
                mode="exec",
                flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
                dont_inherit=True,
            )
        except SyntaxError:
            raise

        if compiled.co_flags & inspect.CO_COROUTINE:
            if asyncio_runner is None:
                raise RuntimeError(
                    "Top-level async code in markdown code blocks requires pytest-asyncio.\n"
                    "Please install pytest-asyncio: pip install pytest-asyncio"
                )
            coro = eval(compiled, args)
            asyncio_runner.run(coro)
        else:
            exec(compiled, args)

    def repr_failure(
        self,
        test: FenceTestDefinition,
        excinfo: pytest.ExceptionInfo[BaseException],
        style=None,
    ) -> str:
        """Renders formatted traceback and line-numbered code snippet."""
        rawlines = test.source.rstrip("\n").split("\n")
        traceback_lines = []
        stack_summary = traceback.StackSummary.extract(traceback.walk_tb(excinfo.tb))
        start_capture = False
        start_line = test.start_line

        for frame_summary in stack_summary:
            if frame_summary.filename == str(test.source_path):
                start_capture = True

            if start_capture:
                lineno = frame_summary.lineno
                line = frame_summary.line or ""
                linespec = f"line {lineno}"
                traceback_lines.append(
                    f'  File "{frame_summary.filename}", {linespec}, in {frame_summary.name}'
                )
                traceback_lines.append(f"    {line.lstrip()}")

        maxdigits = len(str(len(rawlines)))
        code_margin = "   "
        numbered_code = "\n".join(
            [
                f"{i:>{maxdigits}}{code_margin}{line}"
                for i, line in enumerate(rawlines[start_line:], start_line + 1)
            ]
        )

        pretty_traceback = "\n".join(traceback_lines)
        pt = f"Traceback (most recent call last):\n{pretty_traceback}\n{excinfo.exconly()}"

        return (
            f"Error in code block ({test.source_path}:{test.start_line}):\n"
            f"{maxdigits * ' '}{code_margin}```\n"
            f"{numbered_code}\n"
            f"{maxdigits * ' '}{code_margin}```\n"
            f"{pt}\n"
        )


def get_runner(name: typing.Optional[str]) -> _Runner:
    """Retrieve runner by name or return default."""
    if name is None:
        assert _default_runner is not None, "No default runner registered"
        return _default_runner

    if name not in _registered_runners:
        raise KeyError(f"No such py-md-docs runner registered: {name}")
    return _registered_runners[name]
