"""Main Coordinator Agent for the Constructor workflow.

This module creates and exports the main coordinator agent that orchestrates
the course construction process by delegating to specialized sub-agents.

All agent invocations are traced with LangSmith for observability.
"""

from deepagents import create_deep_agent

from app.agents.base.llm import get_llm
from app.agents.constructor.tools.db_tools import (
    save_module,
    save_unit,
    save_material,
    save_quiz,
    save_quiz_question,
    get_uploaded_files,
)
from app.agents.constructor.tools.user_interaction_tools import (
    ask_user,
    get_user_answer,
)
from app.agents.constructor.tools.ingestion_tools import (
    extract_text_from_pdf,
    extract_text_from_slides,
    transcribe_video_file,
    extract_text_from_document,
)
from .prompts import (
    MAIN_COORDINATOR_PROMPT,
    STRUCTURE_SUB_AGENT_PROMPT,
    INGESTION_SUB_AGENT_PROMPT,
    QUIZ_GEN_SUB_AGENT_PROMPT,
    VALIDATION_SUB_AGENT_PROMPT,
)

# LangSmith metadata for tracing
LANGSMITH_METADATA = {
    "project": "agentic-tutor",
    "workflow": "course-construction",
    "agent_type": "coordinator",
    "subagents": ["structure", "ingestion", "quiz-gen", "validation"],
}

# Get the LLM instance
llm = get_llm()

# Sub-agents defined as dictionaries following the SubAgent schema
# Each sub-agent has: name, description, system_prompt, tools (optional)

structure_sub_agent = {
    "name": "structure-sub-agent",
    "description": "Creates comprehensive course structure with modules, units, and content mapping. Use AFTER ingestion has processed all content files, so you know what materials are available to map to units.",
    "system_prompt": STRUCTURE_SUB_AGENT_PROMPT,
    "tools": [
        save_module,
        save_unit,
    ],
}

ingestion_sub_agent = {
    "name": "ingestion-sub-agent",
    "description": "Processes uploaded course materials (PDFs, videos, slides) into text and organizes them into a context folder. Use when ALL content files have been uploaded and need to be processed.",
    "system_prompt": INGESTION_SUB_AGENT_PROMPT,
    "tools": [
        get_uploaded_files,
        save_material,
        extract_text_from_pdf,
        extract_text_from_slides,
        transcribe_video_file,
        extract_text_from_document,
    ],
}

quiz_gen_sub_agent = {
    "name": "quiz-gen-sub-agent",
    "description": "Generates quiz questions based on course content. Each quiz covers content from the unit's materials PLUS all content since the previous quiz. Use after structure-agent has created the course blueprint.",
    "system_prompt": QUIZ_GEN_SUB_AGENT_PROMPT,
    "tools": [
        save_quiz,
        save_quiz_question,
    ],
}

validation_sub_agent = {
    "name": "validation-sub-agent",
    "description": "Performs comprehensive final validation of the course. Returns structured validation result with is_valid (true/false) and feedback. Use at the end of course creation.",
    "system_prompt": VALIDATION_SUB_AGENT_PROMPT,
    "tools": [
        # No database tools - only file system tools for reviewing documentation
    ],
}

# Create the main coordinator agent with all sub-agents
# LangSmith tracing will automatically track all agent runs, tool calls, and sub-agent delegation
# Note: Course is auto-created at session start, so initialize_course is not needed here
main_agent = create_deep_agent(
    model=llm,
    system_prompt=MAIN_COORDINATOR_PROMPT,
    tools=[
        # User interaction tools for asking structured questions
        ask_user,
        get_user_answer,
    ],
    subagents=[
        structure_sub_agent,
        ingestion_sub_agent,
        quiz_gen_sub_agent,
        validation_sub_agent,
    ],
    name="constructor-main-agent",
)

__all__ = ["main_agent"]
