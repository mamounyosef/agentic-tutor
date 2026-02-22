"""Constructor Agent Module using DeepAgents.

This module provides a multi-agent system for course creation using LangChain's
deepagents framework. The main coordinator agent delegates to specialized
sub-agents for structure creation, content ingestion, quiz generation, and validation.
"""

from app.agents.constructor.main_agent.agent import main_agent

__all__ = ["main_agent"]
