"""CrewAI tools. Install with: pip install sarnai[crewai]"""

from __future__ import annotations

from typing import Any

try:
    from crewai.tools import BaseTool
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install the extra: pip install sarnai[crewai]") from exc
from pydantic import BaseModel, Field

from . import _tools


class _FindArgs(BaseModel):
    query: str = Field(description="What you need, in plain words")
    limit: int = Field(default=5, description="Maximum services to return")


class _FindAgentsArgs(BaseModel):
    need: str = Field(description="What you need, in plain words")
    limit: int = Field(default=5, description="Maximum services to return")


class _DescribeArgs(BaseModel):
    listing_id: str = Field(description="A listing id, e.g. from find_agents")


class _RegisterArgs(BaseModel):
    name: str = Field(description="The service's name")
    description: str = Field(description="What the service does")
    endpoint_url: str = Field(description="Where the service is reached (https)")
    submit: bool = Field(default=False, description="False: validate only. True: publish.")


class _VerifyOutputArgs(BaseModel):
    expected_schema: Any = Field(description="JSON Schema the output must satisfy")
    submitted_output: Any = Field(description="The output to verify, as JSON")


class _ScoreArgs(BaseModel):
    agent_id: str = Field(description="The AI agent's identifier")


class FindAgentsTool(BaseTool):
    name: str = "find_agents"
    description: str = _tools.FIND_AGENTS_DESCRIPTION
    args_schema: type[BaseModel] = _FindAgentsArgs

    def _run(self, need: str, limit: int = 5) -> str:
        return _tools.find_agents(need, limit)


class FindServiceTool(BaseTool):
    """Original name of FindAgentsTool, kept as an alias."""

    name: str = "find_service"
    description: str = _tools.FIND_SERVICE_DESCRIPTION
    args_schema: type[BaseModel] = _FindArgs

    def _run(self, query: str, limit: int = 5) -> str:
        return _tools.find_service(query, limit)


class DescribeListingTool(BaseTool):
    name: str = "describe_listing"
    description: str = _tools.DESCRIBE_LISTING_DESCRIPTION
    args_schema: type[BaseModel] = _DescribeArgs

    def _run(self, listing_id: str) -> str:
        return _tools.describe_listing(listing_id)


class RegisterMeTool(BaseTool):
    name: str = "register_me"
    description: str = _tools.REGISTER_ME_DESCRIPTION
    args_schema: type[BaseModel] = _RegisterArgs

    def _run(self, name: str, description: str, endpoint_url: str, submit: bool = False) -> str:
        return _tools.register_me(name, description, endpoint_url, submit)


class VerifyOutputTool(BaseTool):
    name: str = "verify_output"
    description: str = _tools.VERIFY_OUTPUT_DESCRIPTION
    args_schema: type[BaseModel] = _VerifyOutputArgs

    def _run(self, expected_schema: Any, submitted_output: Any) -> str:
        return _tools.verify_output(expected_schema, submitted_output)


class AgentScoreTool(BaseTool):
    name: str = "agent_score"
    description: str = _tools.AGENT_SCORE_DESCRIPTION
    args_schema: type[BaseModel] = _ScoreArgs

    def _run(self, agent_id: str) -> str:
        return _tools.agent_score(agent_id)


find_agents = FindAgentsTool()
find_service = FindServiceTool()
describe_listing = DescribeListingTool()
register_me = RegisterMeTool()
verify_output = VerifyOutputTool()
agent_score = AgentScoreTool()

# `tools` is unchanged from v0.1.x so existing code keeps its tool names.
tools = [find_service, verify_output]
# Everything, without the find_service alias.
all_tools = [find_agents, describe_listing, register_me, verify_output, agent_score]

__all__ = ["FindAgentsTool", "FindServiceTool", "DescribeListingTool", "RegisterMeTool",
           "VerifyOutputTool", "AgentScoreTool", "find_agents", "find_service",
           "describe_listing", "register_me", "verify_output", "agent_score", "tools",
           "all_tools"]
