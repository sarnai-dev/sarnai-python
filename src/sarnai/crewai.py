"""CrewAI tools. Install with: pip install sarnai[crewai]"""

from __future__ import annotations

from typing import Any

try:
    from crewai.tools import BaseTool
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install the extra: pip install sarnai[crewai]") from exc
from pydantic import BaseModel, Field

from . import _tools


class _FindServiceArgs(BaseModel):
    query: str = Field(description="What you need, in plain words")
    limit: int = Field(default=5, description="Maximum listings to return")


class _VerifyOutputArgs(BaseModel):
    expected_schema: Any = Field(description="JSON Schema the output must satisfy")
    submitted_output: Any = Field(description="The output to verify, as JSON")


class FindServiceTool(BaseTool):
    name: str = "find_service"
    description: str = _tools.FIND_SERVICE_DESCRIPTION
    args_schema: type[BaseModel] = _FindServiceArgs

    def _run(self, query: str, limit: int = 5) -> str:
        return _tools.find_service(query, limit)


class VerifyOutputTool(BaseTool):
    name: str = "verify_output"
    description: str = _tools.VERIFY_OUTPUT_DESCRIPTION
    args_schema: type[BaseModel] = _VerifyOutputArgs

    def _run(self, expected_schema: Any, submitted_output: Any) -> str:
        return _tools.verify_output(expected_schema, submitted_output)


find_service = FindServiceTool()
verify_output = VerifyOutputTool()
tools = [find_service, verify_output]
__all__ = ["FindServiceTool", "VerifyOutputTool", "find_service", "verify_output", "tools"]
