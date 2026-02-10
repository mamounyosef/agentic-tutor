"""Nodes for the Session Coordinator graph.

These nodes handle the flow of a tutoring session, routing to different
modes (explainer, gap_analysis, quiz) based on student state.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.base.llm import get_llm
from app.vector.constructor_store import ConstructorVectorStore
from app.vector.student_store import get_student_store
from app.agents.tutor.tools.assessment import (
    get_quiz_question,
    get_quiz_questions_batch,
    grade_multiple_choice,
    grade_answer,
)
from app.agents.tutor.tools.mastery import (
    check_spaced_repetition,
    get_mastery_snapshot,
    get_topic_mastery,
    identify_weak_topics,
    update_mastery_score,
)
from app.agents.tutor.tools.rag import (
    get_student_context,
    get_topic_summary,
    retrieve_for_explanation,
    retrieve_topic_content,
    semantic_search_course,
)
from ..tutor.tools.session import (
    check_session_end_conditions,
    end_tutor_session,
    generate_session_summary,
    get_session_state,
    log_interaction,
    log_student_feedback,
    start_tutor_session,
    update_session_progress,
)
from .prompts import (
    COORDINATOR_DECISION_TEMPLATE,
    EXPLAINER_CLARIFY_TEMPLATE,
    EXPLAINER_REVIEW_TEMPLATE,
    EXPLAINER_SYSTEM_TEMPLATE,
    SESSION_SUMMARY_TEMPLATE,
    WELCOME_SYSTEM_TEMPLATE,
    format_gaps_list,
    format_mastery_overview,
    get_personality_instruction,
)
from .state import TutorState, create_initial_tutor_state

logger = logging.getLogger(__name__)


# =============================================================================
# WELCOME NODES
# =============================================================================

async def welcome_node(state: TutorState) -> Dict[str, Any]:
    """
    Welcome the student and initialize the session.

    Loads mastery snapshot, student context, and generates a personalized welcome.
    """
    logger.info(f"Welcome node for session {state['session_id']}")

    student_id = state["student_id"]
    course_id = state["course_id"]
    session_id = state["session_id"]

    # Start the session
    await start_tutor_session(
        student_id=student_id,
        course_id=course_id,
        goal=state.get("session_goal"),
        session_length_minutes=30,
    )

    # Load mastery snapshot
    mastery_result = await get_mastery_snapshot(
        student_id=student_id,
        course_id=course_id,
    )

    mastery_snapshot = mastery_result.get("mastery_by_topic", {})
    weak_topics = [int(tid) for tid, score in mastery_snapshot.items() if score < 0.5]

    # Get spaced repetition topics
    spaced_result = await check_spaced_repetition(
        student_id=student_id,
        course_id=course_id,
        days_threshold=7,
    )
    topics_due_for_review = spaced_result.get("topics_due_for_review", [])

    # Get student context
    context_result = await get_student_context(
        student_id=student_id,
        course_id=course_id,
    )

    # Get course info for welcome message
    course_store = ConstructorVectorStore(course_id)
    course_info = await _get_course_info(course_store, course_id)

    # Format mastery overview
    mastery_overview = format_mastery_overview(
        mastery_snapshot,
        course_info.get("topics", [])
    )

    # Generate welcome message
    welcome_prompt = WELCOME_SYSTEM_TEMPLATE.format(
        course_title=course_info.get("title", "this course"),
        student_name=f"Student {student_id}",
        time_enrolled="some time",
        mastery_overview=mastery_overview or "Starting fresh!",
    )

    llm = get_llm(temperature=0.7)
    response = await llm.ainvoke(welcome_prompt)
    welcome_message = response.content if hasattr(response, 'content') else str(response)

    return {
        **state,
        "mastery_snapshot": mastery_snapshot,
        "weak_topics": weak_topics,
        "topics_due_for_review": topics_due_for_review,
        "student_context": context_result.get("student_context") if context_result.get("success") else None,
        "messages": state["messages"] + [{
            "role": "assistant",
            "content": welcome_message,
        }],
        "current_mode": "intake",
        "last_activity_at": datetime.utcnow().isoformat(),
    }


async def intake_node(state: TutorState) -> Dict[str, Any]:
    """
    Process student input and determine next action.

    This node analyzes the student's message and decides what to do next.
    """
    logger.info(f"Intake node for session {state['session_id']}")

    # Get the last message (student's input)
    messages = state.get("messages", [])
    if not messages:
        return {
            **state,
            "next_action": "ask_goal",
            "action_rationale": "No messages, asking for session goal",
        }

    last_message = messages[-1]
    content = last_message.get("content", "")

    # Log the interaction
    await log_interaction(
        session_id=state["session_id"],
        student_id=state["student_id"],
        course_id=state["course_id"],
        interaction_type="question",
        content=content,
        topic_id=state.get("current_topic", {}).get("id") if state.get("current_topic") else None,
    )

    # Check for explicit requests
    content_lower = content.lower()

    if "quiz" in content_lower or "test" in content_lower:
        return {
            **state,
            "next_action": "quiz",
            "action_rationale": "Student explicitly requested a quiz",
        }

    if "help" in content_lower or "stuck" in content_lower or "confused" in content_lower:
        return {
            **state,
            "next_action": "clarify",
            "action_rationale": "Student indicates confusion or needs help",
        }

    if "review" in content_lower:
        return {
            **state,
            "next_action": "review",
            "action_rationale": "Student requested review",
        }

    if "gap" in content_lower or "weak" in content_lower or "improve" in content_lower:
        return {
            **state,
            "next_action": "gap_analysis",
            "action_rationale": "Student wants to address gaps",
        }

    if "bye" in content_lower or "done" in content_lower or "finish" in content_lower:
        return {
            **state,
            "should_end": True,
            "end_reason": "Student requested to end session",
            "next_action": "summarize",
        }

    # Use LLM to decide next action based on context
    return await _decide_next_action(state, content)


# =============================================================================
# DECISION NODES
# =============================================================================

async def _decide_next_action(state: TutorState, user_message: str) -> Dict[str, Any]:
    """Use LLM to decide the next action."""
    student_context = state.get("student_context") or {}
    sentiment_summary = student_context.get("sentiment", {})

    # Format decision prompt
    decision_prompt = COORDINATOR_DECISION_TEMPLATE.format(
        student_name=f"Student {state['student_id']}",
        current_mode=state.get("current_mode", "welcome"),
        session_goal=state.get("session_goal", "General learning"),
        topics_covered=state.get("topics_covered", []),
        interactions_count=state.get("interactions_count", 0),
        time_elapsed=_calculate_time_elapsed(state),
        mastery_snapshot=format_mastery_overview(
            state.get("mastery_snapshot", {}),
            []  # Topics would be loaded from course
        ),
        weak_topics=state.get("weak_topics", []),
        due_for_review=state.get("topics_due_for_review", []),
        sentiment=sentiment_summary.get("overall_sentiment", "neutral"),
    )

    llm = get_llm(temperature=0.3)
    response = await llm.ainvoke(decision_prompt + f"\n\nStudent said: \"{user_message}\"")

    # Parse the decision from the response
    response_text = response.content if hasattr(response, 'content') else str(response)
    response_lower = response_text.lower()

    # Simple keyword-based decision extraction
    if "gap_analysis" in response_lower or "identify gaps" in response_lower:
        next_action = "gap_analysis"
    elif "review" in response_lower and "spaced" in response_lower:
        next_action = "review"
    elif "clarify" in response_lower or "confused" in response_lower:
        next_action = "clarify"
    elif "quiz" in response_lower:
        next_action = "quiz"
    elif "teach" in response_lower or "explain" in response_lower or "new topic" in response_lower:
        next_action = "teach"
    elif "summarize" in response_lower or "end" in response_lower:
        next_action = "summarize"
    else:
        # Default based on state
        if state.get("weak_topics") and state.get("weak_topics")[0] if state.get("weak_topics") else None:
            next_action = "gap_analysis"
        elif state.get("topics_due_for_review"):
            next_action = "review"
        else:
            next_action = "teach"

    return {
        **state,
        "next_action": next_action,
        "action_rationale": f"LLM decided based on: {response_text[:100]}...",
    }


def _calculate_time_elapsed(state: TutorState) -> int:
    """Calculate minutes elapsed since session start."""
    try:
        started = datetime.fromisoformat(state.get("session_started_at", ""))
        elapsed = (datetime.utcnow() - started).total_seconds() / 60
        return int(elapsed)
    except Exception:
        return 0


def route_by_action(state: TutorState) -> str:
    """Route to the appropriate mode based on next_action."""
    action = state.get("next_action", "teach")

    action_mapping = {
        "teach": "explainer",
        "review": "explainer",
        "clarify": "explainer",
        "gap_analysis": "gap_analysis",
        "quiz": "quiz",
        "summarize": "summarize",
        "ask_goal": "respond",
    }

    return action_mapping.get(action, "explainer")


def should_continue(state: TutorState) -> str:
    """Check if the session should continue or end."""
    if state.get("should_end", False):
        return "end"

    # Check session conditions
    elapsed = _calculate_time_elapsed(state)
    if elapsed > 60:  # 60 minute max session
        return "end"

    return "continue"


# =============================================================================
# EXPLAINER NODES
# =============================================================================

async def explainer_node(state: TutorState) -> Dict[str, Any]:
    """
    Provide explanations using RAG from course content.

    This node handles:
    - Teaching new topics
    - Reviewing previously learned topics
    - Clarifying confusion
    """
    logger.info(f"Explainer node for session {state['session_id']}")

    student_id = state["student_id"]
    course_id = state["course_id"]
    action = state.get("next_action", "teach")

    # Determine what topic to explain
    topic_to_explain = await _select_topic_for_explanation(state)

    if not topic_to_explain:
        return {
            **state,
            "messages": state["messages"] + [{
                "role": "assistant",
                "content": "I couldn't find a specific topic to explain. Could you tell me what you'd like to learn about?",
            }],
            "next_action": "ask_goal",
        }

    # Get retrieval context for explanation
    retrieval_result = await retrieve_for_explanation(
        student_id=student_id,
        course_id=course_id,
        topic_id=topic_to_explain["id"],
        student_query=state.get("messages", [])[-1].get("content", "") if state.get("messages") else "",
        include_student_context=True,
    )

    # Get student context for personalization
    student_context = state.get("student_context") or {}
    sentiment_summary = student_context.get("sentiment", {"overall_sentiment": "neutral"})

    # Get topic mastery
    mastery_result = await get_topic_mastery(
        student_id=student_id,
        course_id=course_id,
        topic_id=topic_to_explain["id"],
    )
    current_mastery = mastery_result.get("score", 0.0)

    # Generate appropriate explanation prompt
    if action == "review":
        # Review mode - spaced repetition
        prompt = EXPLAINER_REVIEW_TEMPLATE.format(
            student_name=f"Student {student_id}",
            topic_title=topic_to_explain.get("title", "this topic"),
            days_since_review="several",
            current_mastery=int(current_mastery * 100),
        )
    elif action == "clarify":
        # Clarification mode
        prompt = EXPLAINER_CLARIFY_TEMPLATE.format(
            student_name=f"Student {student_id}",
            topic_title=topic_to_explain.get("title", "this topic"),
            student_question=state.get("messages", [])[-1].get("content", "") if state.get("messages") else "",
            identified_confusion="the main concept",
            current_mastery=int(current_mastery * 100),
        )
    else:
        # Teaching mode
        learning_style = student_context.get("learning_style", {})
        personality_instruction = get_personality_instruction(
            sentiment=sentiment_summary.get("overall_sentiment", "neutral"),
            recent_feedback=student_context.get("recent_feedback", []),
            current_mastery=current_mastery,
        )

        prompt = EXPLAINER_SYSTEM_TEMPLATE.format(
            topic_title=topic_to_explain.get("title", "this topic"),
            learning_style=learning_style or "Not yet determined",
            sentiment=sentiment_summary.get("overall_sentiment", "neutral"),
            misconceptions=student_context.get("misconceptions", []),
            interaction_summary="Previous interactions will be loaded",
            content_summary="Course content retrieved from vector DB",
            personality_instruction=personality_instruction,
        )

    # Get explanation from LLM
    llm = get_llm(temperature=0.7)
    response = await llm.ainvoke(prompt)
    explanation = response.content if hasattr(response, 'content') else str(response)

    # Update state
    new_topics_covered = state.get("topics_covered", [])
    if topic_to_explain["id"] not in new_topics_covered:
        new_topics_covered.append(topic_to_explain["id"])

    return {
        **state,
        "current_topic": topic_to_explain,
        "explanation_given": explanation,
        "topics_covered": new_topics_covered,
        "interactions_count": state.get("interactions_count", 0) + 1,
        "messages": state["messages"] + [{
            "role": "assistant",
            "content": explanation,
        }],
        "current_mode": "explainer",
        "last_activity_at": datetime.utcnow().isoformat(),
    }


async def _select_topic_for_explanation(state: TutorState) -> Optional[Dict[str, Any]]:
    """Select the appropriate topic to explain based on state and action."""
    action = state.get("next_action", "teach")
    course_id = state["course_id"]

    course_store = ConstructorVectorStore(course_id)

    if action == "review" and state.get("topics_due_for_review"):
        # Get first topic due for review
        topic_id = state["topics_due_for_review"][0]
        result = await get_topic_summary(
            student_id=state["student_id"],
            course_id=course_id,
            topic_id=topic_id,
        )
        if result.get("success"):
            return {
                "id": topic_id,
                "title": result.get("metadata", {}).get("title", f"Topic {topic_id}"),
                "summary": result.get("summary", ""),
            }

    elif state.get("weak_topics"):
        # Get first weak topic
        topic_id = state["weak_topics"][0]
        result = await get_topic_summary(
            student_id=state["student_id"],
            course_id=course_id,
            topic_id=topic_id,
        )
        if result.get("success"):
            return {
                "id": topic_id,
                "title": result.get("metadata", {}).get("title", f"Topic {topic_id}"),
                "summary": result.get("summary", ""),
            }

    else:
        # Get first topic from course
        # This would normally get the next uncompleted topic
        results = course_store.similarity_search(
            query="",
            collection_name=ConstructorVectorStore.COLLECTION_TOPICS,
            k=1,
        )
        if results:
            metadata = results[0].get("metadata", {})
            return {
                "id": int(metadata.get("topic_id", 1)),
                "title": metadata.get("title", "Introduction"),
                "summary": results[0].get("content", ""),
            }

    return None


# =============================================================================
# GAP ANALYSIS NODES
# =============================================================================

async def gap_analysis_node(state: TutorState) -> Dict[str, Any]:
    """
    Analyze knowledge gaps and create a remediation plan.

    Identifies topics where the student is struggling and prioritizes
    what to work on next.
    """
    logger.info(f"Gap analysis node for session {state['session_id']}")

    student_id = state["student_id"]
    course_id = state["course_id"]

    # Identify weak topics
    weak_result = await identify_weak_topics(
        student_id=student_id,
        course_id=course_id,
        threshold=0.5,
        include_prerequisites=True,
    )

    weak_topics_data = weak_result.get("weak_topics", [])

    # Format gaps for display
    gaps_list = []
    course_store = ConstructorVectorStore(course_id)

    for weak_topic in weak_topics_data:
        topic_id = weak_topic.get("topic_id")
        mastery = weak_topic.get("mastery", 0.0)

        # Get topic info
        result = await get_topic_summary(
            student_id=student_id,
            course_id=course_id,
            topic_id=topic_id,
        )

        if result.get("success"):
            gaps_list.append({
                "topic_id": topic_id,
                "topic_title": result.get("metadata", {}).get("title", f"Topic {topic_id}"),
                "current_mastery": mastery,
                "required_mastery": 0.7,
                "priority": "high" if mastery < 0.3 else "medium",
                "is_prerequisite_for": [],  # Would be loaded from DB
            })

    # Generate gap analysis message
    if gaps_list:
        gaps_text = format_gaps_list(gaps_list)

        message = f"""I've analyzed your knowledge gaps. Here's what I found:

{gaps_text}

Let's focus on {gaps_list[0]['topic_title']} first. It's important for progressing in the course.

Would you like me to explain this topic, or would you prefer to start with something else?"""
    else:
        message = "Great news! I don't see any significant knowledge gaps. You're doing well. Would you like to move on to a new topic?"

    return {
        **state,
        "identified_gaps": gaps_list,
        "weak_topics": [g["topic_id"] for g in gaps_list],
        "messages": state["messages"] + [{
            "role": "assistant",
            "content": message,
        }],
        "current_mode": "gap_analysis",
        "last_activity_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# QUIZ NODES (Hard-coded, no LLM)
# =============================================================================

async def quiz_node(state: TutorState) -> Dict[str, Any]:
    """
    Administer a quiz (hard-coded assessment, no LLM grading).

    Gets quiz questions from the bank and tracks progress.
    """
    logger.info(f"Quiz node for session {state['session_id']}")

    student_id = state["student_id"]
    course_id = state["course_id"]

    # If no active quiz, start one
    if not state.get("current_quiz"):
        # Select topics to quiz based on weak areas or current topic
        topic_ids = state.get("weak_topics", [])
        if not topic_ids and state.get("current_topic"):
            topic_ids = [state["current_topic"]["id"]]

        if not topic_ids:
            # Get first topic from course
            topic_ids = [1]  # Default to topic 1

        # Get quiz questions
        quiz_result = await get_quiz_questions_batch(
            student_id=student_id,
            course_id=course_id,
            topic_ids=topic_ids,
            count_per_topic=3,
        )

        questions_by_topic = quiz_result.get("questions_by_topic", {})
        all_questions = []
        for topic_qs in questions_by_topic.values():
            all_questions.extend(topic_qs)

        if not all_questions:
            return {
                **state,
                "messages": state["messages"] + [{
                    "role": "assistant",
                    "content": "I don't have any quiz questions ready for this topic yet. Let's continue learning!",
                }],
                "next_action": "teach",
            }

        return {
            **state,
            "current_quiz": {
                "questions": all_questions,
                "total": len(all_questions),
            },
            "quiz_position": 0,
            "quiz_score": 0.0,
            "quiz_start_time": datetime.utcnow().isoformat(),
            "quiz_completed": False,
        }

    # Check if quiz is complete
    current_quiz = state["current_quiz"]
    position = state.get("quiz_position", 0)
    total = current_quiz.get("total", 1)

    if position >= total:
        # Quiz complete, show results
        return await _finalize_quiz(state)

    # Get current question
    questions = current_quiz.get("questions", [])
    current_question = questions[position] if position < len(questions) else None

    if not current_question:
        return await _finalize_quiz(state)

    # Present the question
    question_text = current_question.get("question_text", "")
    question_type = current_question.get("question_type", "multiple_choice")
    options = current_question.get("options", [])

    if question_type == "multiple_choice" and options:
        options_text = "\n".join([
            f"{chr(65 + i)}) {opt.get('text', opt)}"
            for i, opt in enumerate(options)
        ])
        message = f"""Question {position + 1} of {total}:

{question_text}

{options_text}

Please enter your answer (A, B, C, or D)."""
    else:
        message = f"""Question {position + 1} of {total}:

{question_text}

Please enter your answer."""

    return {
        **state,
        "messages": state["messages"] + [{
            "role": "assistant",
            "content": message,
        }],
        "current_mode": "quiz",
    }


async def grade_quiz_node(state: TutorState) -> Dict[str, Any]:
    """
    Grade the student's quiz answer (hard-coded, no LLM).

    Extracts the answer from the last message and grades it.
    """
    logger.info(f"Grade quiz node for session {state['session_id']}")

    # Get student's answer from last message
    messages = state.get("messages", [])
    if not messages:
        return state

    last_message = messages[-1]
    student_answer = last_message.get("content", "").strip()

    # Get current question
    current_quiz = state.get("current_quiz", {})
    questions = current_quiz.get("questions", [])
    position = state.get("quiz_position", 0)

    if position >= len(questions):
        return await _finalize_quiz(state)

    current_question = questions[position]

    # Grade the answer (hard-coded)
    grade_result = await grade_answer(
        student_id=state["student_id"],
        course_id=state["course_id"],
        topic_id=current_question.get("topic_id", 1),
        question=current_question,
        student_answer=student_answer,
    )

    is_correct = grade_result.get("is_correct", False)
    score = grade_result.get("score", 0.0)

    # Record the attempt
    await record_quiz_attempt(
        student_id=state["student_id"],
        course_id=state["course_id"],
        topic_id=current_question.get("topic_id", 1),
        question_id=current_question.get("id", 0),
        student_answer=student_answer,
        is_correct=is_correct,
        score=score,
    )

    # Generate feedback message (simple, no LLM)
    if is_correct:
        feedback = f"✅ Correct! Great job."
    else:
        correct_answer = current_question.get("correct_answer", "")
        feedback = f"❌ Not quite right. The correct answer is: {correct_answer}"

    # Move to next question
    new_position = position + 1
    new_score = state.get("quiz_score", 0.0) + score

    return {
        **state,
        "quiz_position": new_position,
        "quiz_score": new_score,
        "messages": state["messages"] + [{
            "role": "assistant",
            "content": feedback,
        }],
        "interactions_count": state.get("interactions_count", 0) + 1,
    }


async def record_quiz_attempt(
    student_id: int,
    course_id: int,
    topic_id: int,
    question_id: int,
    student_answer: str,
    is_correct: bool,
    score: float,
) -> Dict[str, Any]:
    """Record a quiz attempt (simplified version that doesn't use the tool directly)."""
    # This would record to the database
    # For now, we'll just log it
    logger.info(
        f"Quiz attempt recorded: Student {student_id}, Course {course_id}, "
        f"Topic {topic_id}, Question {question_id}, Correct: {is_correct}, Score: {score}"
    )
    return {"success": True}


async def _finalize_quiz(state: TutorState) -> Dict[str, Any]:
    """Finalize the quiz and show results."""
    current_quiz = state.get("current_quiz", {})
    total = current_quiz.get("total", 1)
    score = state.get("quiz_score", 0.0)
    start_time = state.get("quiz_start_time")

    # Calculate time taken
    time_taken = "N/A"
    if start_time:
        try:
            start = datetime.fromisoformat(start_time)
            elapsed = (datetime.utcnow() - start).total_seconds()
            time_taken = f"{int(elapsed)} seconds"
        except Exception:
            pass

    percentage = int((score / total) * 100) if total > 0 else 0

    message = f"""📊 Quiz Results!

You scored: {score}/{total} ({percentage}%)
Time taken: {time_taken}

{'🎉 Excellent work!' if percentage >= 80 else '👍 Good effort! Keep practicing.' if percentage >= 60 else '💪 Keep working at it. Review the material and try again.'}

Would you like to:
- Review the topics you missed
- Try another quiz
- Move on to new content
- End the session"""

    return {
        **state,
        "messages": state["messages"] + [{
            "role": "assistant",
            "content": message,
        }],
        "quiz_completed": True,
        "current_quiz": None,
        "current_mode": "respond",
        "last_activity_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# SUMMARY NODES
# =============================================================================

async def summarize_node(state: TutorState) -> Dict[str, Any]:
    """
    Generate a session summary and end the session.

    Shows progress, improvements, and next steps.
    """
    logger.info(f"Summarize node for session {state['session_id']}")

    # Generate session summary
    summary_result = await generate_session_summary(
        session_id=state["session_id"],
        student_id=state["student_id"],
        course_id=state["course_id"],
    )

    # Calculate session metrics
    duration = _calculate_time_elapsed(state)
    topics_covered = state.get("topics_covered", [])
    interactions = state.get("interactions_count", 0)

    # Get mastery comparison
    initial_mastery = state.get("mastery_snapshot", {})
    # In real implementation, would get final mastery snapshot

    # Generate summary message
    summary = f"""📚 Session Summary

Session Duration: {duration} minutes
Topics Covered: {len(topics_covered)}
Interactions: {interactions}

Progress made this session! Here's what we covered:
{', '.join([f'Topic {tid}' for tid in topics_covered]) if topics_covered else 'Getting started'}

Recommended next steps:
"""

    if state.get("weak_topics"):
        summary += f"- Focus on improving weak topics\n"
    if state.get("topics_due_for_review"):
        summary += f"- Review topics due for spaced repetition\n"
    if not state.get("weak_topics") and not state.get("topics_due_for_review"):
        summary += f"- Continue with the next module\n"

    summary += f"\nGreat work today! Come back soon to continue learning. 🎓"

    # End the session
    await end_tutor_session(
        session_id=state["session_id"],
        student_id=state["student_id"],
        course_id=state["course_id"],
        summary=summary,
    )

    return {
        **state,
        "messages": state["messages"] + [{
            "role": "assistant",
            "content": summary,
        }],
        "session_summary": summary,
        "should_end": True,
        "end_reason": "Session completed",
        "current_mode": "end",
        "last_activity_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# ROUTING FUNCTIONS
# =============================================================================

def route_after_explainer(state: TutorState) -> str:
    """Decide what to do after an explanation."""
    # Check if we should quiz or continue teaching
    if state.get("interactions_count", 0) % 3 == 0:  # Every 3 interactions, suggest quiz
        return "quiz"
    return "intake"


def route_after_quiz(state: TutorState) -> str:
    """Decide what to do after quiz."""
    if state.get("quiz_completed", False):
        return "intake"
    return "grade"


async def _get_course_info(course_store: ConstructorVectorStore, course_id: int) -> Dict[str, Any]:
    """Get basic course information."""
    # This would query the database for course info
    return {
        "id": course_id,
        "title": f"Course {course_id}",
        "topics": [],
    }
