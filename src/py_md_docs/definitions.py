"""Data definitions for py-md-docs test cases."""

import pathlib
import typing
from dataclasses import dataclass


@dataclass(frozen=True)
class FenceTestDefinition:
    """Represents an extracted code fence test definition."""

    source: str
    fixture_names: typing.Sequence[str]
    start_line: int
    source_path: pathlib.Path
    runner_name: typing.Optional[str] = None
    max_retries: int = 0


@dataclass(frozen=True)
class ObjectTestDefinition:
    """Represents a docstring test extracted from a Python class, function, or method."""

    intra_object_index: int
    object_name: str
    fence_test: FenceTestDefinition
