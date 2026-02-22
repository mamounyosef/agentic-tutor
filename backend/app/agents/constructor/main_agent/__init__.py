"""Main Coordinator Agent using DeepAgents.

This module contains the main coordinator agent that orchestrates
the course construction workflow by delegating to specialized sub-agents.
"""

from .agent import main_agent

__all__ = ["main_agent"]
