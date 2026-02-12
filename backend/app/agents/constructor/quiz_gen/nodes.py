"""Node functions for the Quiz Generation Agent.

Each node represents a step in the quiz generation workflow:
1. plan_quiz_generation - Plan the quiz generation strategy
2. select_next_topic - Select the next topic to process
3. generate_questions - Generate questions for current topic
4. validate_questions - Validate generated questions
5. create_rubrics - Create grading rubrics
6. check_completion - Check if all topics are done
7. finalize_quiz_bank - Finalize and prepare for storage
"""

import json
import logging
from typing import Any, Dict, List

from app.agents.constructor.state import QuizQuestionInfo
from app.agents.constructor.tools.quiz import (
    create_quiz_rubric,
    generate_multiple_choice,
    generate_quiz_question,
    generate_short_answer,
    generate_true_false,
)
from .prompts import COMPLETION_MESSAGE, PLAN_QUIZ_GENERATION_PROMPT
from .state import (
    GeneratedQuestion,
    QuizGenState,
    TopicQuizResult,
)

logger = logging.getLogger(__name__)


async def plan_quiz_generation_node(state: QuizGenState) -> Dict[str, Any]:
    """
    Plan the quiz generation strategy for all topics.

    Determines how many questions to generate per topic and
    the distribution of types and difficulty.
    """
    topics = state.get("topics", [])
    target_questions_per_topic = state.get("target_questions_per_topic", 5)
    course_title = state.get("course_title", "")

    if not topics:
        return {
            "errors": ["No topics to generate questions for"],
            "phase": "plan",
        }

    # Create a simple plan - equal distribution for all topics
    # In production, this could use LLM to customize per topic
    quiz_plan = []
    for topic in topics:
        topic_title = topic.get("title", "")
        topic_description = topic.get("description", "")

        # Adjust question count based on topic complexity
        # More complex topics get more questions
        base_count = target_questions_per_topic
        description_length = len(topic_description)
        if description_length > 200:
            base_count += 2
        elif description_length < 50:
            base_count = max(3, base_count - 2)

        # Distribute question types (60% MCQ, 25% TF, 15% Short Answer)
        mcq_count = int(base_count * 0.6)
        tf_count = int(base_count * 0.25)
        sa_count = base_count - mcq_count - tf_count

        # Distribute difficulty (30% Easy, 50% Medium, 20% Hard)
        easy_count = int(base_count * 0.3)
        medium_count = int(base_count * 0.5)
        hard_count = base_count - easy_count - medium_count

        quiz_plan.append({
            "topic_title": topic_title,
            "topic_data": topic,
            "question_count": base_count,
            "types": {
                "multiple_choice": mcq_count,
                "true_false": tf_count,
                "short_answer": max(1, sa_count),
            },
            "difficulty": {
                "easy": easy_count,
                "medium": medium_count,
                "hard": max(1, hard_count),
            },
        })

    return {
        "quiz_plan": quiz_plan,
        "phase": "select_topic",
    }


async def select_next_topic_node(state: QuizGenState) -> Dict[str, Any]:
    """
    Select the next topic to process.

    Returns the next topic that needs questions generated.
    """
    quiz_plan = state.get("quiz_plan", [])
    current_index = state.get("current_topic_index", 0)
    completed_topics = state.get("topics_completed", 0)

    if current_index >= len(quiz_plan):
        # All topics processed
        return {
            "phase": "finalize",
            "generation_complete": True,
        }

    # Get the next topic plan
    topic_plan = quiz_plan[current_index]
    topic_data = topic_plan.get("topic_data", {})

    return {
        "current_topic": topic_data,
        "current_topic_plan": topic_plan,
        "phase": "generate_questions",
    }


async def generate_questions_node(state: QuizGenState) -> Dict[str, Any]:
    """
    Generate quiz questions for the current topic.

    Uses the quiz tools to generate questions based on the plan.
    """
    current_topic = state.get("current_topic", {})
    topic_plan = state.get("current_topic_plan", {})
    content_chunks = state.get("content_chunks", [])

    topic_title = current_topic.get("title", "")
    topic_description = current_topic.get("description", "")

    # Find relevant content chunks for this topic
    # Simple keyword matching - could be enhanced with vector search
    relevant_chunks = []
    topic_keywords = topic_title.lower().split()

    for chunk in content_chunks:
        chunk_text = chunk.get("text", "").lower()
        # Check if any topic keyword appears in chunk
        if any(keyword in chunk_text for keyword in topic_keywords if len(keyword) > 3):
            relevant_chunks.append(chunk)

    # If no relevant chunks found, use first few chunks
    if not relevant_chunks:
        relevant_chunks = content_chunks[:3]

    # Combine relevant chunks for content
    combined_content = "\n\n".join([
        chunk.get("text", "") for chunk in relevant_chunks
    ])[:3000]  # Limit content length

    # Get question type distribution from plan
    types_distribution = topic_plan.get("types", {})
    difficulty_distribution = topic_plan.get("difficulty", {})

    generated_questions: List[GeneratedQuestion] = []
    errors = []

    # Generate multiple choice questions
    mcq_count = types_distribution.get("multiple_choice", 0)
    for difficulty, count in difficulty_distribution.items():
        # Generate portion of MCQ for this difficulty
        mcq_for_difficulty = max(1, int(mcq_count * count / sum(difficulty_distribution.values()) or 1))

        for _ in range(mcq_for_difficulty):
            result = await generate_multiple_choice.ainvoke({
                "topic_title": topic_title,
                "content": combined_content,
                "difficulty": difficulty,
            })

            if result.get("success"):
                q_data = result.get("question", {})
                generated_questions.append(GeneratedQuestion(
                    question_type="multiple_choice",
                    question_text=q_data.get("question_text", ""),
                    options=q_data.get("options", []),
                    correct_answer=_extract_correct_answer(q_data),
                    explanation=q_data.get("explanation", ""),
                    difficulty=difficulty,
                    topic_title=topic_title,
                    rubric=None,
                ))
            else:
                errors.append(f"MCQ generation failed: {result.get('error')}")

    # Generate true/false questions
    tf_count = types_distribution.get("true_false", 0)
    for difficulty, count in difficulty_distribution.items():
        tf_for_difficulty = max(1, int(tf_count * count / sum(difficulty_distribution.values()) or 1))

        for _ in range(tf_for_difficulty):
            result = await generate_true_false.ainvoke({
                "topic_title": topic_title,
                "content": combined_content,
                "difficulty": difficulty,
            })

            if result.get("success"):
                q_data = result.get("question", {})
                generated_questions.append(GeneratedQuestion(
                    question_type="true_false",
                    question_text=q_data.get("question_text", ""),
                    options=None,
                    correct_answer=q_data.get("correct_answer", ""),
                    explanation=q_data.get("explanation", ""),
                    difficulty=difficulty,
                    topic_title=topic_title,
                    rubric=None,
                ))
            else:
                errors.append(f"TF generation failed: {result.get('error')}")

    # Generate short answer questions
    sa_count = types_distribution.get("short_answer", 1)
    for difficulty, count in difficulty_distribution.items():
        sa_for_difficulty = max(1, int(sa_count * count / sum(difficulty_distribution.values()) or 1))

        for _ in range(sa_for_difficulty):
            result = await generate_short_answer.ainvoke({
                "topic_title": topic_title,
                "content": combined_content,
                "difficulty": difficulty,
            })

            if result.get("success"):
                q_data = result.get("question", {})
                generated_questions.append(GeneratedQuestion(
                    question_type="short_answer",
                    question_text=q_data.get("question_text", ""),
                    options=None,
                    correct_answer=q_data.get("sample_answer", ""),
                    explanation=q_data.get("grading_notes", ""),
                    difficulty=difficulty,
                    topic_title=topic_title,
                    rubric=None,
                ))
            else:
                errors.append(f"Short answer generation failed: {result.get('error')}")

    # Create topic quiz result
    topic_result = TopicQuizResult(
        topic_title=topic_title,
        topic_id=current_topic.get("id"),
        questions=generated_questions,
        total_questions=len(generated_questions),
        questions_by_type=_count_by_type(generated_questions),
        questions_by_difficulty=_count_by_difficulty(generated_questions),
        success=len(generated_questions) > 0,
        errors=errors,
    )

    return {
        "current_topic_result": topic_result,
        "phase": "validate_questions",
    }


async def validate_questions_node(state: QuizGenState) -> Dict[str, Any]:
    """
    Validate generated questions for quality.

    Checks for answerability, clarity, and correctness.
    """
    topic_result = state.get("current_topic_result")
    validation_warnings = []
    validation_errors = []

    if not topic_result:
        return {
            "validation_errors": ["No topic result to validate"],
            "phase": "validate_questions",
        }

    questions = topic_result.get("questions", [])

    for i, question in enumerate(questions):
        # Basic validation checks
        question_text = question.get("question_text", "")

        if not question_text or len(question_text) < 10:
            validation_errors.append(f"Question {i+1}: Question text too short or empty")
            continue

        # Check for MCQ specific issues
        if question.get("question_type") == "multiple_choice":
            options = question.get("options", [])
            if not options or len(options) != 4:
                validation_warnings.append(f"Question {i+1}: MCQ should have exactly 4 options")

            # Check that exactly one option is correct
            correct_count = sum(1 for opt in options if opt.get("is_correct", False))
            if correct_count != 1:
                validation_errors.append(f"Question {i+1}: MCQ must have exactly 1 correct answer, found {correct_count}")

        # Check for true/false specific issues
        if question.get("question_type") == "true_false":
            correct_answer = question.get("correct_answer", "").lower()
            if correct_answer not in ["true", "false"]:
                validation_errors.append(f"Question {i+1}: True/False must have 'true' or 'false' as answer")

        # Check for short answer specific issues
        if question.get("question_type") == "short_answer":
            correct_answer = question.get("correct_answer", "")
            if not correct_answer or len(correct_answer) < 10:
                validation_warnings.append(f"Question {i+1}: Short answer should have a sample answer")

    # Update topic result with validation status
    topic_result["validation_passed"] = len(validation_errors) == 0
    topic_result["validation_warnings"] = validation_warnings
    topic_result["validation_errors"] = validation_errors

    return {
        "current_topic_result": topic_result,
        "validation_errors": validation_errors,
        "validation_warnings": validation_warnings,
        "phase": "create_rubrics",
    }


async def create_rubrics_node(state: QuizGenState) -> Dict[str, Any]:
    """
    Create grading rubrics for short answer questions.

    Generates rubrics for subjective question types.
    """
    topic_result = state.get("current_topic_result", {})
    rubrics = {}

    if not topic_result:
        return {
            "phase": "check_completion",
        }

    questions = topic_result.get("questions", [])

    for i, question in enumerate(questions):
        # Only create rubrics for short answer questions
        if question.get("question_type") != "short_answer":
            continue

        question_text = question.get("question_text", "")
        correct_answer = question.get("correct_answer", "")

        # Extract key points from explanation
        explanation = question.get("explanation", "")
        key_points = explanation.split(". ")[:3] if explanation else []

        # Create rubric using the tool
        result = await create_quiz_rubric.ainvoke({
            "question_text": question_text,
            "question_type": "short_answer",
            "sample_answer": correct_answer,
            "key_points": key_points,
        })

        if result.get("success"):
            rubric_data = result.get("rubric", {})
            rubrics[f"{topic_result.get('topic_title')}_{i}"] = rubric_data

            # Update question with rubric
            question["rubric"] = rubric_data

    return {
        "rubrics": rubrics,
        "current_topic_result": topic_result,
        "phase": "check_completion",
    }


async def check_completion_node(state: QuizGenState) -> Dict[str, Any]:
    """
    Check if all topics have been processed.

    Either moves to the next topic or proceeds to finalization.
    """
    current_index = state.get("current_topic_index", 0)
    quiz_plan = state.get("quiz_plan", [])
    topic_result = state.get("current_topic_result")
    topic_quizzes = state.get("topic_quizzes", [])
    all_questions = state.get("all_questions", [])

    # Add current topic result to the list
    if topic_result:
        topic_quizzes.append(topic_result)
        all_questions.extend(topic_result.get("questions", []))

    # Move to next topic
    next_index = current_index + 1

    if next_index >= len(quiz_plan):
        # All topics done
        return {
            "current_topic_index": next_index,
            "topic_quizzes": topic_quizzes,
            "all_questions": all_questions,
            "topics_completed": len(topic_quizzes),
            "generation_complete": True,
            "phase": "finalize",
        }

    return {
        "current_topic_index": next_index,
        "topic_quizzes": topic_quizzes,
        "all_questions": all_questions,
        "topics_completed": len(topic_quizzes),
        "phase": "select_topic",
    }


async def finalize_quiz_bank_node(state: QuizGenState) -> Dict[str, Any]:
    """
    Finalize the quiz bank and prepare for database storage.

    Converts generated questions to the database format.
    """
    all_questions = state.get("all_questions", [])
    topic_quizzes = state.get("topic_quizzes", [])
    rubrics = state.get("rubrics", {})

    # Calculate statistics
    total_questions = len(all_questions)
    questions_by_type = _count_by_type(all_questions)
    questions_by_difficulty = _count_by_difficulty(all_questions)

    # Convert to QuizQuestionInfo format for database
    quiz_questions_for_db: List[QuizQuestionInfo] = []
    mapping_errors: List[str] = []
    topic_id_by_title = {
        str(topic_result.get("topic_title", "")).strip().lower(): topic_result.get("topic_id")
        for topic_result in topic_quizzes
        if str(topic_result.get("topic_title", "")).strip()
    }

    for question in all_questions:
        # Convert options format for MCQ
        options = None
        if question.get("question_type") == "multiple_choice":
            options = question.get("options", [])

        resolved_topic_id = question.get("topic_id")
        if resolved_topic_id is None:
            topic_title_key = str(question.get("topic_title", "")).strip().lower()
            resolved_topic_id = topic_id_by_title.get(topic_title_key)

        if resolved_topic_id is None:
            mapping_errors.append(
                f"Could not map topic_id for quiz question: {question.get('question_text', '')[:80]}"
            )
            continue

        quiz_questions_for_db.append(QuizQuestionInfo(
            id=None,
            topic_id=int(resolved_topic_id),
            question_text=question.get("question_text", ""),
            question_type=question.get("question_type", ""),
            options=options,
            correct_answer=question.get("correct_answer", ""),
            difficulty=question.get("difficulty", "medium"),
            rubric=json.dumps(question.get("rubric", {})),
        ))

    # Count validation issues
    total_errors = sum(len(t.get("validation_errors", [])) for t in topic_quizzes)
    total_warnings = sum(len(t.get("validation_warnings", [])) for t in topic_quizzes)

    # Generate completion message
    completion_msg = COMPLETION_MESSAGE.format(
        topics_completed=len(topic_quizzes),
        topics_total=state.get("topics_total", len(topic_quizzes)),
        total_questions=total_questions,
        type_breakdown=json.dumps(questions_by_type),
        difficulty_breakdown=json.dumps(questions_by_difficulty),
        passed_count=total_questions - total_errors,
        issue_count=total_errors + total_warnings,
    )

    return {
        "questions_by_type": questions_by_type,
        "questions_by_difficulty": questions_by_difficulty,
        "quiz_questions_for_db": quiz_questions_for_db,
        "total_questions_generated": total_questions,
        "phase": "complete",
        "generation_complete": True,
        "errors": [*state.get("errors", []), *mapping_errors],
    }


# Helper functions

def _extract_correct_answer(question_data: Dict[str, Any]) -> str:
    """Extract the correct answer from MCQ options."""
    options = question_data.get("options", [])
    for opt in options:
        if opt.get("is_correct", False):
            return opt.get("text", "")
    return ""


def _count_by_type(questions: List[GeneratedQuestion]) -> Dict[str, int]:
    """Count questions by type."""
    counts = {"multiple_choice": 0, "true_false": 0, "short_answer": 0}
    for q in questions:
        qtype = q.get("question_type", "")
        if qtype in counts:
            counts[qtype] += 1
    return counts


def _count_by_difficulty(questions: List[GeneratedQuestion]) -> Dict[str, int]:
    """Count questions by difficulty."""
    counts = {"easy": 0, "medium": 0, "hard": 0}
    for q in questions:
        difficulty = q.get("difficulty", "medium")
        if difficulty in counts:
            counts[difficulty] += 1
    return counts
