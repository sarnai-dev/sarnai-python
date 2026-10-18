"""LangChain tools. Install with: pip install sarnai[langchain]"""

from __future__ import annotations

from typing import Any

try:
    from langchain_core.tools import StructuredTool
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install the extra: pip install sarnai[langchain]") from exc

from . import _tools


def _tool(func: Any, name: str, description: str) -> StructuredTool:
    return StructuredTool.from_function(func=func, name=name, description=description)


find_agents = _tool(
    lambda need, limit=5: _tools.find_agents(need, limit), "find_agents",
    _tools.FIND_AGENTS_DESCRIPTION)

# Original name, kept as an alias of find_agents.
find_service = _tool(
    lambda query, limit=5: _tools.find_service(query, limit), "find_service",
    _tools.FIND_SERVICE_DESCRIPTION)

describe_listing = _tool(
    lambda listing_id: _tools.describe_listing(listing_id), "describe_listing",
    _tools.DESCRIBE_LISTING_DESCRIPTION)

register_me = _tool(
    lambda name, description, endpoint_url, submit=False, connections=None,
    payment_methods=None: _tools.register_me(
        name, description, endpoint_url, submit, connections, payment_methods),
    "register_me", _tools.REGISTER_ME_DESCRIPTION)


def _verify(expected_schema: Any, submitted_output: Any) -> str:
    return _tools.verify_output(expected_schema, submitted_output)


verify_output = _tool(_verify, "verify_output", _tools.VERIFY_OUTPUT_DESCRIPTION)

agent_score = _tool(
    lambda agent_id: _tools.agent_score(agent_id), "agent_score", _tools.AGENT_SCORE_DESCRIPTION)

# `tools` is unchanged from v0.1.x so existing code keeps its tool names.
tools = [find_service, verify_output]
# Everything, without the find_service alias.
all_tools = [find_agents, describe_listing, register_me, verify_output, agent_score]

__all__ = ["find_agents", "find_service", "describe_listing", "register_me", "verify_output",
           "agent_score", "tools", "all_tools"]
