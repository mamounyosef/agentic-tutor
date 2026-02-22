"""Main Coordinator Agent for the Constructor workflow.

This module creates and exports the main coordinator agent that orchestrates
the course construction process by delegating to specialized sub-agents.
"""

from deepagents import create_deep_agent

from app.agents.base.llm import get_llm
from app.agents.constructor.tools.db_tools import initialize_course
from .prompts import MAIN_COORDINATOR_PROMPT

# Get the LLM instance
llm = get_llm()

# Create the main coordinator agent
# Note: Sub-agents will be added in subsequent steps
main_agent = create_deep_agent(
    model=llm,
    system_prompt=MAIN_COORDINATOR_PROMPT,
    tools=[
        initialize_course,  # Only direct DB access for main agent
    ],
    subagents=[],  # Sub-agents will be added: structure, ingestion, quiz, validation
    name="constructor-main-agent",
)

__all__ = ["main_agent"]
