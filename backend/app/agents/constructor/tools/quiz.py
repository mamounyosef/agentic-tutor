"""Quiz generation tools for creating assessment questions.

Tools for generating multiple choice, true/false, and short answer questions
from course content.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from app.agents.base.llm import get_llm

logger = logging.getLogger(__name__)


# =============================================================================
# Question Generation Prompts
# =============================================================================

MCQ_PROMPT = """Generate a {difficulty} multiple choice question based on the following content.

Topic: {topic_title}
Content:
{content}

Create a clear, unambiguous question with exactly 4 options. Only one option should be correct.
The question should test understanding of key concepts, not just memorization.

Return JSON:
{{
  "question_text": "The question text?",
  "options": [
    {{"text": "Option A", "is_correct": false}},
    {{"text": "Option B", "is_correct": true}},
    {{"text": "Option C", "is_correct": false}},
    {{"text": "Option D", "is_correct": false}}
  ],
  "explanation": "Brief explanation of why the correct answer is correct"
}}
"""


TRUE_FALSE_PROMPT = """Generate a {difficulty} true/false question based on the following content.

Topic: {topic_title}
Content:
{content}

Create a statement that tests understanding of a key concept. The statement should be
clearly either true or false based on the content.

Return JSON:
{{
  "question_text": "The statement to evaluate",
  "correct_answer": "true",
  "explanation": "Brief explanation"
}}
"""


SHORT_ANSWER_PROMPT = """Generate a {difficulty} short answer question based on the following content.

Topic: {topic_title}
Content:
{content}

Create an open-ended question that requires a brief written response (1-3 sentences).
The question should test understanding and application of concepts.

Return JSON:
{{
  "question_text": "The question text",
  "sample_answer": "A model answer that would receive full marks",
  "key_points": ["point1", "point2", "point3"],
  "grading_notes": "What to look for in student responses"
}}
"""


# =============================================================================
# Multiple Choice Questions
# =============================================================================

@tool
async def generate_multiple_choice(
    topic_title: str,
    content: str,
    difficulty: str = "medium",
) -> Dict[str, Any]:
    """
    Generate a multiple choice question from topic content.

    Args:
        topic_title: Title of the topic
        content: Content to generate question from
        difficulty: Difficulty level (easy, medium, hard)

    Returns:
        Dictionary with question data
    """
    try:
        llm = get_llm(temperature=0.7)

        prompt = MCQ_PROMPT.format(
            difficulty=difficulty,
            topic_title=topic_title,
            content=content[:2000],  # Limit content length
        )

        response = await llm.ainvoke(prompt)
        content_text = response.content

        # Parse JSON
        if "```json" in content_text:
            content_text = content_text.split("```json")[1].split("```")[0]
        elif "```" in content_text:
            content_text = content_text.split("```")[1].split("```")[0]

        question_data = json.loads(content_text.strip())

        # Add metadata
        question_data["question_type"] = "multiple_choice"
        question_data["difficulty"] = difficulty
        question_data["topic_title"] = topic_title

        return {
            "success": True,
            "question": question_data,
        }

    except Exception as e:
        logger.error(f"Error generating MCQ: {e}")
        return {
            "success": False,
            "error": str(e),
            "question": None,
        }


# =============================================================================
# True/False Questions
# =============================================================================

@tool
async def generate_true_false(
    topic_title: str,
    content: str,
    difficulty: str = "medium",
) -> Dict[str, Any]:
    """
    Generate a true/false question from topic content.

    Args:
        topic_title: Title of the topic
        content: Content to generate question from
        difficulty: Difficulty level (easy, medium, hard)

    Returns:
        Dictionary with question data
    """
    try:
        llm = get_llm(temperature=0.7)

        prompt = TRUE_FALSE_PROMPT.format(
            difficulty=difficulty,
            topic_title=topic_title,
            content=content[:2000],
        )

        response = await llm.ainvoke(prompt)
        content_text = response.content

        # Parse JSON
        if "```json" in content_text:
            content_text = content_text.split("```json")[1].split("```")[0]
        elif "```" in content_text:
            content_text = content_text.split("```")[1].split("```")[0]

        question_data = json.loads(content_text.strip())

        # Add metadata
        question_data["question_type"] = "true_false"
        question_data["difficulty"] = difficulty
        question_data["topic_title"] = topic_title

        return {
            "success": True,
            "question": question_data,
        }

    except Exception as e:
        logger.error(f"Error generating true/false: {e}")
        return {
            "success": False,
            "error": str(e),
            "question": None,
        }


# =============================================================================
# Short Answer Questions
# =============================================================================

@tool
async def generate_short_answer(
    topic_title: str,
    content: str,
    difficulty: str = "medium",
) -> Dict[str, Any]:
    """
    Generate a short answer question from topic content.

    Args:
        topic_title: Title of the topic
        content: Content to generate question from
        difficulty: Difficulty level (easy, medium, hard)

    Returns:
        Dictionary with question data
    """
    try:
        llm = get_llm(temperature=0.7)

        prompt = SHORT_ANSWER_PROMPT.format(
            difficulty=difficulty,
            topic_title=topic_title,
            content=content[:2000],
        )

        response = await llm.ainvoke(prompt)
        content_text = response.content

        # Parse JSON
        if "```json" in content_text:
            content_text = content_text.split("```json")[1].split("```")[0]
        elif "```" in content_text:
            content_text = content_text.split("```")[1].split("```")[0]

        question_data = json.loads(content_text.strip())

        # Add metadata
        question_data["question_type"] = "short_answer"
        question_data["difficulty"] = difficulty
        question_data["topic_title"] = topic_title

        return {
            "success": True,
            "question": question_data,
        }

    except Exception as e:
        logger.error(f"Error generating short answer: {e}")
        return {
            "success": False,
            "error": str(e),
            "question": None,
        }


# =============================================================================
# Unified Question Generation
# =============================================================================

@tool
async def generate_quiz_question(
    topic_title: str,
    content: str,
    question_type: str = "multiple_choice",
    difficulty: str = "medium",
) -> Dict[str, Any]:
    """
    Generate a quiz question of specified type from topic content.

    Args:
        topic_title: Title of the topic
        content: Content to generate question from
        question_type: Type of question (multiple_choice, true_false, short_answer)
        difficulty: Difficulty level (easy, medium, hard)

    Returns:
        Dictionary with question data
    """
    if question_type == "multiple_choice":
        return await generate_multiple_choice.ainvoke({
            "topic_title": topic_title,
            "content": content,
            "difficulty": difficulty,
        })
    elif question_type == "true_false":
        return await generate_true_false.ainvoke({
            "topic_title": topic_title,
            "content": content,
            "difficulty": difficulty,
        })
    elif question_type == "short_answer":
        return await generate_short_answer.ainvoke({
            "topic_title": topic_title,
            "content": content,
            "difficulty": difficulty,
        })
    else:
        return {
            "success": False,
            "error": f"Unknown question type: {question_type}",
            "question": None,
        }


# =============================================================================
# Rubric Creation
# =============================================================================

RUBRIC_PROMPT = """Create a grading rubric for the following question.

Question: {question_text}
Type: {question_type}
Sample Answer: {sample_answer}
Key Points: {key_points}

Create a rubric that can be used to grade student responses on a 0-100 scale.

Return JSON:
{{
  "criteria": [
    {{
      "name": "Criterion name",
      "description": "What this criterion assesses",
      "max_points": 25,
      "levels": [
        {{"score": 25, "description": "Excellent"}},
        {{"score": 18, "description": "Good"}},
        {{"score": 10, "description": "Fair"}},
        {{"score": 0, "description": "Poor"}}
      ]
    }}
  ],
  "total_points": 100,
  "grading_instructions": "Overall guidance for grading"
}}
"""


@tool
async def create_quiz_rubric(
    question_text: str,
    question_type: str,
    sample_answer: str,
    key_points: List[str],
) -> Dict[str, Any]:
    """
    Create a grading rubric for a question.

    Args:
        question_text: The question text
        question_type: Type of question
        sample_answer: A model answer
        key_points: Key points that should be covered

    Returns:
        Dictionary with rubric data
    """
    try:
        llm = get_llm(temperature=0.5)

        prompt = RUBRIC_PROMPT.format(
            question_text=question_text,
            question_type=question_type,
            sample_answer=sample_answer,
            key_points=json.dumps(key_points),
        )

        response = await llm.ainvoke(prompt)
        content_text = response.content

        # Parse JSON
        if "```json" in content_text:
            content_text = content_text.split("```json")[1].split("```")[0]
        elif "```" in content_text:
            content_text = content_text.split("```")[1].split("```")[0]

        rubric_data = json.loads(content_text.strip())

        return {
            "success": True,
            "rubric": rubric_data,
        }

    except Exception as e:
        logger.error(f"Error creating rubric: {e}")
        return {
            "success": False,
            "error": str(e),
            "rubric": None,
        }
