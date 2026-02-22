"""Structure Sub-Agent for the Constructor workflow.

This agent creates comprehensive course structures (modules and units)
with logical progression and appropriate prerequisites.
"""

from deepagents import create_deep_agent

from app.agents.base.llm import get_llm
from app.agents.constructor.tools.db_tools import save_module, save_unit
from ..main_agent.prompts import STRUCTURE_SUB_AGENT_PROMPT

# Get the LLM instance
llm = get_llm()

# Create the structure sub-agent
structure_sub_agent = create_deep_agent(
    model=llm,
    system_prompt=STRUCTURE_SUB_AGENT_PROMPT,
    tools=[
        save_module,
        save_unit,
        # File system tools are built-in with deepagents
    ],
    subagents=[],  # No sub-agents for this specialist
    name="structure-sub-agent",
)

__all__ = ["structure_sub_agent"]
