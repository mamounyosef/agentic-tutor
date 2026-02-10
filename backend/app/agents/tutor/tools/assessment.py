"""Assessment tools for Tutor agents.

These tools enable:
- Retrieving quiz questions
- Grading student answers (multiple choice, text)
- Generating personalized feedback
- Identifying misconceptions from wrong answers
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from app.agents.base.llm import get_llm
from app.vector.constructor_store import ConstructorVectorStore
from app.vector.student_store import get_student_store

logger = logging.getLogger(__name__)


# =============================================================================
# Quiz Question Retrieval
# =============================================================================

@tool
async def get_quiz_question(
    student_id: int,
    course_id: int,
    topic_id: int,
    difficulty: str = "medium",
    exclude_seen: bool = True,
    question_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get a quiz question from the course question bank.

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_id: The topic to get a question for
        difficulty: Desired difficulty (easy, medium, hard)
        exclude_seen: Whether to exclude questions the student has already seen
        question_type: Optional type filter (multiple_choice, true_false, short_answer)

    Returns:
        Quiz question with metadata
    """
    try:
        course_store = ConstructorVectorStore(course_id)

        # Search for questions matching criteria
        filter_metadata = {
            "topic_id": str(topic_id),
            "difficulty": difficulty,
        }

        if question_type:
            filter_metadata["question_type"] = question_type

        # TODO: If exclude_seen, check student's quiz_attempts table
        # and filter out already-seen question IDs

        results = course_store.similarity_search(
            query="",  # Get all matching filter
            collection_name=ConstructorVectorStore.COLLECTION_QUESTIONS,
            k=1,
            filter_metadata=filter_metadata
        )

        if results:
            # TODO: Get full question details from MySQL (quiz_questions table)
            # including options, correct_answer, rubric
            return {
                "success": True,
                "question": {
                    "id": results[0].get("metadata", {}).get("question_id", ""),
                    "question_text": results[0].get("content", ""),
                    "metadata": results[0].get("metadata", {}),
                },
            }
        else:
            return {
                "success": False,
                "error": "No matching question found",
                "topic_id": topic_id,
                "difficulty": difficulty,
            }

    except Exception as e:
        logger.error(f"Error getting quiz question: {e}")
        return {
            "success": False,
            "error": str(e),
            "topic_id": topic_id,
        }


@tool
async def get_quiz_questions_batch(
    student_id: int,
    course_id: int,
    topic_ids: List[int],
    count_per_topic: int = 3
) -> Dict[str, Any]:
    """
    Get a batch of quiz questions for multiple topics.

    Useful for generating a quiz covering several topics.

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_ids: List of topics to include
        count_per_topic: Number of questions per topic

    Returns:
        Batch of quiz questions organized by topic
    """
    try:
        questions_by_topic = {}

        for topic_id in topic_ids:
            # Get questions for each topic (mix of difficulties)
            questions = []
            for difficulty in ["easy", "medium", "hard"]:
                result = await get_quiz_question(
                    student_id=student_id,
                    course_id=course_id,
                    topic_id=topic_id,
                    difficulty=difficulty,
                    exclude_seen=True,
                )

                if result.get("success") and result.get("question"):
                    questions.append(result["question"])
                    if len(questions) >= count_per_topic:
                        break

            if questions:
                questions_by_topic[str(topic_id)] = questions

        return {
            "success": True,
            "questions_by_topic": questions_by_topic,
            "total_questions": sum(len(q) for q in questions_by_topic.values()),
        }

    except Exception as e:
        logger.error(f"Error getting question batch: {e}")
        return {
            "success": False,
            "error": str(e),
            "questions_by_topic": {},
        }


# =============================================================================
# Answer Grading
# =============================================================================

@tool
async def grade_multiple_choice(
    student_id: int,
    course_id: int,
    question: Dict[str, Any],
    student_answer: str
) -> Dict[str, Any]:
    """
    Grade a multiple choice question.

    Args:
        student_id: The student's ID
        course_id: The course's ID
        question: The question with options and correct answer
        student_answer: The student's selected answer

    Returns:
        Grading result with correctness and score
    """
    try:
        correct_answer = question.get("correct_answer", "")
        options = question.get("options", [])

        # Normalize for comparison
        student_answer_normalized = student_answer.strip().lower()
        correct_answer_normalized = correct_answer.strip().lower()

        is_correct = student_answer_normalized == correct_answer_normalized

        # Calculate partial credit if enabled
        # (e.g., if A is correct and student selected "A, B" might give 0.5)
        score = 1.0 if is_correct else 0.0

        return {
            "success": True,
            "is_correct": is_correct,
            "score": score,
            "correct_answer": correct_answer,
            "student_answer": student_answer,
            "question_type": "multiple_choice",
        }

    except Exception as e:
        logger.error(f"Error grading multiple choice: {e}")
        return {
            "success": False,
            "error": str(e),
            "is_correct": False,
            "score": 0.0,
        }


@tool
async def grade_with_rubric(
    student_id: int,
    course_id: int,
    topic_id: int,
    question: Dict[str, Any],
    student_answer: str
) -> Dict[str, Any]:
    """
    Grade a short answer or essay question using LLM and rubric.

    Uses LLM to:
    1. Compare student answer to rubric criteria
    2. Assess completeness and accuracy
    3. Assign a score (0-1)
    4. Generate specific feedback

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_id: The topic for context
        question: The question with rubric
        student_answer: The student's answer text

    Returns:
        Grading result with score and feedback
    """
    try:
        llm = get_llm(temperature=0.3)

        # Get relevant content for context
        context_result = await retrieve_topic_content(
            student_id=student_id,
            course_id=course_id,
            topic_id=topic_id,
            query=question.get("question_text", ""),
            k=3
        )

        context_text = "\n\n".join([
            chunk.get("content", "") for chunk in context_result.get("chunks", [])
        ])

        rubric = question.get("rubric", "")
        question_text = question.get("question_text", "")

        grading_prompt = f"""You are an expert tutor grading a student's answer.

Question: {question_text}

Rubric:
{rubric}

Relevant course content for context:
{context_text}

Student's Answer:
{student_answer}

Grade the answer on a scale of 0.0 to 1.0 based on:
- Accuracy: Does the answer correctly address the question?
- Completeness: Does it cover all key points from the rubric?
- Understanding: Does the student demonstrate understanding?

Respond in JSON format:
{{
    "score": <0.0 to 1.0>,
    "is_correct": <true if score >= 0.6 else false>,
    "feedback": "<specific, constructive feedback>",
    "strengths": ["<what they did well>"],
    "areas_for_improvement": ["<what to work on>"]
}}
"""

        response = await llm.ainvoke(grading_prompt)

        # Parse JSON response
        import json

        try:
            # Try to extract JSON from response
            response_text = response.content if hasattr(response, 'content') else response
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            grading_result = json.loads(response_text)

            return {
                "success": True,
                **grading_result,
                "question_type": "short_answer",
            }

        except json.JSONDecodeError:
            # Fallback to simple scoring
            logger.warning(f"Failed to parse LLM grading response, using fallback")

            # Simple keyword matching for fallback
            answer_lower = student_answer.lower()
            question_lower = question_text.lower()

            # Check if answer contains relevant keywords
            keywords = question_lower.split()[:5]  # First 5 words as keywords
            matches = sum(1 for kw in keywords if kw in answer_lower)
            score = min(matches / len(keywords), 1.0)

            return {
                "success": True,
                "score": score,
                "is_correct": score >= 0.6,
                "feedback": "Please review your answer and try again.",
                "strengths": [],
                "areas_for_improvement": ["Be more comprehensive in your answer"],
                "question_type": "short_answer",
            }

    except Exception as e:
        logger.error(f"Error grading with rubric: {e}")
        return {
            "success": False,
            "error": str(e),
            "score": 0.0,
            "is_correct": False,
        }


@tool
async def grade_answer(
    student_id: int,
    course_id: int,
    topic_id: int,
    question: Dict[str, Any],
    student_answer: str
) -> Dict[str, Any]:
    """
    Route to appropriate grading method based on question type.

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_id: The topic for context
        question: The question to grade
        student_answer: The student's answer

    Returns:
        Grading result
    """
    question_type = question.get("question_type", "multiple_choice")

    if question_type == "multiple_choice":
        return await grade_multiple_choice(
            student_id=student_id,
            course_id=course_id,
            question=question,
            student_answer=student_answer
        )

    elif question_type == "true_false":
        # Similar to multiple choice
        return await grade_multiple_choice(
            student_id=student_id,
            course_id=course_id,
            question=question,
            student_answer=student_answer
        )

    else:  # short_answer, essay
        return await grade_with_rubric(
            student_id=student_id,
            course_id=course_id,
            topic_id=topic_id,
            question=question,
            student_answer=student_answer
        )


# =============================================================================
# Feedback Generation
# =============================================================================

@tool
async def generate_feedback(
    student_id: int,
    course_id: int,
    topic_id: int,
    question: Dict[str, Any],
    student_answer: str,
    grading_result: Dict[str, Any],
    include_explanation: bool = True
) -> Dict[str, Any]:
    """
    Generate personalized feedback for a student's answer.

    Uses LLM to create:
    1. Specific feedback on their answer
    2. Explanation of the correct answer
    3. Guidance for improvement
    4. Encouragement tailored to student's learning style

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_id: The topic for context
        question: The question that was asked
        student_answer: The student's answer
        grading_result: The grading outcome
        include_explanation: Whether to include correct answer explanation

    Returns:
        Personalized feedback
    """
    try:
        # Get student context for personalization
        student_store = get_student_store(student_id, course_id)
        sentiment = await student_store.get_student_sentiment_summary()

        llm = get_llm(temperature=0.7)

        is_correct = grading_result.get("is_correct", False)
        score = grading_result.get("score", 0.0)

        # Personalize tone based on sentiment
        overall_sentiment = sentiment.get("overall_sentiment", "neutral")
        if overall_sentiment == "negative":
            tone_instruction = "Be extra encouraging and supportive. The student is struggling."
        elif overall_sentiment == "positive":
            tone_instruction = "Be concise and acknowledge their good progress."
        else:
            tone_instruction = "Be balanced and clear."

        feedback_prompt = f"""Generate personalized feedback for a student's answer.

Question: {question.get('question_text', '')}

Student's Answer: {student_answer}

Result: {'Correct' if is_correct else 'Incorrect'}, Score: {score:.1f}/1.0

{tone_instruction}

Generate a concise, helpful feedback that:
1. Acknowledges their answer
2. Explains why it's correct or incorrect
3. Provides guidance for improvement
4. Is encouraging and supportive

Keep it to 2-3 sentences max.
"""

        response = await llm.ainvoke(feedback_prompt)

        feedback_text = response.content if hasattr(response, 'content') else response

        return {
            "success": True,
            "feedback": feedback_text.strip(),
            "is_correct": is_correct,
            "score": score,
            "personalized": True,
        }

    except Exception as e:
        logger.error(f"Error generating feedback: {e}")

        # Fallback feedback
        is_correct = grading_result.get("is_correct", False)
        if is_correct:
            feedback = "Great job! Your answer is correct."
        else:
            feedback = "Not quite right. Review the material and try again."

        return {
            "success": True,
            "feedback": feedback,
            "is_correct": is_correct,
            "personalized": False,
        }


@tool
async def identify_misconception_from_answer(
    student_id: int,
    course_id: int,
    topic_id: int,
    question: Dict[str, Any],
    student_answer: str
) -> Dict[str, Any]:
    """
    Identify if the student's answer reveals a misconception.

    Uses LLM to analyze wrong answers and identify specific misconceptions.
    Records the misconception for future reference.

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_id: The topic
        question: The question
        student_answer: The student's (wrong) answer

    Returns:
        Identified misconception (if any)
    """
    try:
        llm = get_llm(temperature=0.3)

        analysis_prompt = f"""Analyze this incorrect student answer to identify the misconception.

Question: {question.get('question_text', '')}

Correct Answer: {question.get('correct_answer', '')}

Student's (Incorrect) Answer: {student_answer}

Identify the specific misconception or misunderstanding. What concept
is the student getting wrong? Be specific and concise.

Respond in JSON:
{{
    "has_misconception": <true/false>,
    "concept": "<the concept being misunderstood>",
    "misconception": "<what the student is getting wrong>",
    "severity": "<minor/moderate/severe>"
}}

If the answer is simply a mistake (not a misconception), set has_misconception to false.
"""

        response = await llm.ainvoke(analysis_prompt)

        # Parse JSON
        import json

        try:
            response_text = response.content if hasattr(response, 'content') else response
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            result = json.loads(response_text)

            if result.get("has_misconception"):
                # Record the misconception
                student_store = get_student_store(student_id, course_id)
                await student_store.record_misconception(
                    student_id=student_id,
                    course_id=course_id,
                    topic_id=topic_id,
                    concept=result.get("concept", ""),
                    misconception=result.get("misconception", "")
                )

            return {
                "success": True,
                **result,
            }

        except json.JSONDecodeError:
            return {
                "success": True,
                "has_misconception": False,
            }

    except Exception as e:
        logger.error(f"Error identifying misconception: {e}")
        return {
            "success": False,
            "error": str(e),
            "has_misconception": False,
        }
