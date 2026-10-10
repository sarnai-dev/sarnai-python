"""LangChain tools. Install with: pip install sarnai[langchain]"""

from __future__ import annotations

from typing import Any

try:
    from langchain_core.tools import StructuredTool
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install the extra: pip install sarnai[langchain]") from exc

from . import _tools

find_service = StructuredTool.from_function(
    func=lambda query, limit=5: _tools.find_service(query, limit),
    name="find_service",
    description=_tools.FIND_SERVICE_DESCRIPTION,
)


def _verify(expected_schema: Any, submitted_output: Any) -> str:
    return _tools.verify_output(expected_schema, submitted_output)


verify_output = StructuredTool.from_function(
    func=_verify,
    name="verify_output",
    description=_tools.VERIFY_OUTPUT_DESCRIPTION,
)

tools = [find_service, verify_output]
__all__ = ["find_service", "verify_output", "tools"]
