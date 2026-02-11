"""Node functions for the Validation Agent.

Each node represents a step in the validation workflow:
1. validate_content - LLM-based content quality assessment
2. validate_structure - LLM-based structure integrity validation
3. validate_quiz - LLM-based quiz quality validation
4. calculate_readiness - Calculate overall readiness score (LLM-assisted)
5. generate_report - Generate final validation report
"""

import json
import logging
from typing import Any, Dict, List, Set

from ...base.llm import get_llm
from .prompts import COMPLETION_MESSAGE
from .state import (
    ContentValidationResult,
    StructureValidationResult,
    ValidationResult,
    ValidationState,
)

logger = logging.getLogger(__name__)


async def validate_content_node(state: ValidationState) -> Dict[str, Any]:
    """
    Validate content quality using LLM assessment.

    LLM evaluates:
    - Content completeness for each topic
    - Quality and depth of material
    - Pedagogical value
    """
    llm = get_llm(temperature=0.3)
    topics = state.get("topics", [])
    content_chunks = state.get("content_chunks", [])

    if not topics:
        return {
            "content_validation": ContentValidationResult(
                topics_without_content=[],
                content_coverage={},
                empty_topics=[],
                total_issues=1,
            ),
            "phase": "validate_structure",
            "errors": ["No topics to validate"],
        }

    # Prepare topics summary for LLM
    topics_summary = []
    for topic in topics:
        topic_title = topic.get("title", "")
        topic_desc = topic.get("description", "")

        # Find related chunks
        related_chunks = []
        for chunk in content_chunks[:5]:  # Limit for token efficiency
            chunk_text = chunk.get("text", "")
            if topic_title.lower() in chunk_text.lower():
                related_chunks.append(chunk_text[:200])

        topics_summary.append({
            "title": topic_title,
            "description": topic_desc,
            "has_chunks": len(related_chunks) > 0,
            "chunks_preview": " ".join(related_chunks[:2]) if related_chunks else "",
        })

    # LLM-based validation prompt
    validation_prompt = f"""You are a course quality validator. Analyze the course content below and validate its quality.

Course: {state.get('course_title', 'Unknown')}

Topics to validate:
{json.dumps(topics_summary, indent=2)}

For each topic, assess:
1. **Content Completeness**: Does the topic have adequate learning material?
2. **Quality**: Is the content well-structured and comprehensive?
3. **Pedagogical Value**: Would this effectively teach a student?

Return JSON:
{{
  "validated_topics": {{
    "Topic Title": {{
      "has_adequate_content": true/false,
      "quality_score": 0.0-1.0,
      "issues": ["list any issues"],
      "coverage_estimate": "high/medium/low"
    }}
  }},
  "overall_assessment": {{
    "topics_without_content": ["list of topics with no content"],
    "empty_topics": ["list of topics with empty descriptions"],
    "content_coverage": {{"Topic Title": 0.0-1.0}},
    "total_issues": count
  }}
}}
"""

    try:
        response = await llm.ainvoke(validation_prompt)
        content = response.content

        # Parse JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result_data = json.loads(content.strip())
        overall = result_data.get("overall_assessment", {})

        result = ContentValidationResult(
            topics_without_content=overall.get("topics_without_content", []),
            content_coverage=overall.get("content_coverage", {}),
            empty_topics=overall.get("empty_topics", []),
            total_issues=overall.get("total_issues", 0),
        )

        return {
            "content_validation": result,
            "phase": "validate_structure",
        }

    except Exception as e:
        logger.error(f"LLM content validation failed: {e}")
        # Fallback to rule-based validation
        return await _fallback_content_validation(state)


async def _fallback_content_validation(state: ValidationState) -> Dict[str, Any]:
    """Fallback rule-based content validation."""
    topics = state.get("topics", [])
    content_chunks = state.get("content_chunks", [])

    topics_without_content: List[str] = []
    empty_topics: List[str] = []
    content_coverage: Dict[str, float] = {}

    for topic in topics:
        topic_title = topic.get("title", "")
        topic_desc = topic.get("description", "")

        if not topic_desc or len(topic_desc) < 20:
            empty_topics.append(topic_title)

        has_chunks = any(
            topic_title.lower() in chunk.get("text", "").lower()
            for chunk in content_chunks
        )

        if not has_chunks:
            topics_without_content.append(topic_title)

        coverage = 1.0 if has_chunks else 0.0
        if topic_desc:
            coverage += 0.5
        coverage = min(1.0, coverage)
        content_coverage[topic_title] = coverage

    result = ContentValidationResult(
        topics_without_content=topics_without_content,
        content_coverage=content_coverage,
        empty_topics=empty_topics,
        total_issues=len(topics_without_content) + len(empty_topics),
    )

    return {
        "content_validation": result,
        "phase": "validate_structure",
    }


async def validate_structure_node(state: ValidationState) -> Dict[str, Any]:
    """
    Validate structure integrity using LLM assessment.

    LLM evaluates:
    - Prerequisite relationships make pedagogical sense
    - Learning progression is logical
    - No circular or problematic dependencies
    """
    llm = get_llm(temperature=0.3)
    topics = state.get("topics", [])
    prerequisite_map = state.get("prerequisite_map", {})

    if not topics:
        return {
            "structure_validation": StructureValidationResult(
                circular_references=[],
                orphaned_topics=[],
                unreachable_topics=[],
                hierarchy_issues=["No topics to validate"],
                total_issues=1,
            ),
            "phase": "validate_quiz",
        }

    # Prepare structure summary for LLM
    topics_list = [t.get("title", "") for t in topics]
    prereqs_summary = []
    for topic, prereqs in prerequisite_map.items():
        if prereqs:
            prereqs_summary.append(f"{topic} requires: {', '.join(prereqs)}")

    # LLM-based structure validation
    validation_prompt = f"""You are a course structure validator. Analyze the course structure for pedagogical soundness.

Course: {state.get('course_title', 'Unknown')}

Topics ({len(topics)}):
{', '.join(topics_list)}

Prerequisite Relationships:
{chr(10).join(prereqs_summary) if prereqs_summary else "No prerequisites defined"}

Analyze the structure for:
1. **Circular References**: Does any topic indirectly require itself?
2. **Pedagogical Logic**: Do prerequisites make sense for learning?
3. **Learning Path**: Is there a logical progression from basics to advanced?
4. **Orphaned Topics**: Are there topics disconnected from the learning path?

Return JSON:
{{
  "circular_references": [["Topic A", "Topic B", "Topic A"]],  # cycles found
  "pedagogical_issues": ["Description of issues with prereqs"],
  "orphaned_topics": ["Topic names with no connections"],
  "unreachable_topics": ["Topic names that cannot be reached"],
  "hierarchy_issues": ["List of structural problems"],
  "quality_assessment": "excellent/good/fair/poor",
  "total_issues": count
}}
"""

    try:
        response = await llm.ainvoke(validation_prompt)
        content = response.content

        # Parse JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result_data = json.loads(content.strip())

        # Also run algorithmic check for circular references as backup
        circular_refs = await _detect_circular_prereqs(topics, prerequisite_map)

        result = StructureValidationResult(
            circular_references=result_data.get("circular_references", circular_refs),
            orphaned_topics=result_data.get("orphaned_topics", []),
            unreachable_topics=result_data.get("unreachable_topics", []),
            hierarchy_issues=result_data.get("hierarchy_issues", []),
            total_issues=result_data.get("total_issues", 0),
        )

        return {
            "structure_validation": result,
            "phase": "validate_quiz",
        }

    except Exception as e:
        logger.error(f"LLM structure validation failed: {e}")
        return await _fallback_structure_validation(state)


async def _detect_circular_prereqs(topics: List[Dict], prerequisite_map: Dict[str, List[str]]) -> List[List[str]]:
    """Algorithmically detect circular prerequisite chains."""
    all_topics = {t.get("title", "") for t in topics}
    circular_refs: List[List[str]] = []
    visited: Set[str] = set()

    def has_cycle(topic: str, path: List[str], rec_stack: Set[str]) -> bool:
        if topic in rec_stack:
            cycle_start = path.index(topic)
            circular_refs.append(path[cycle_start:] + [topic])
            return True
        if topic in visited:
            return False

        visited.add(topic)
        rec_stack.add(topic)
        path.append(topic)

        for prereq in prerequisite_map.get(topic, []):
            if prereq in all_topics and has_cycle(prereq, path, rec_stack):
                return True

        path.pop()
        rec_stack.remove(topic)
        return False

    for topic in all_topics:
        if topic not in visited:
            has_cycle(topic, [], set())

    return circular_refs


async def _fallback_structure_validation(state: ValidationState) -> Dict[str, Any]:
    """Fallback rule-based structure validation."""
    topics = state.get("topics", [])
    prerequisite_map = state.get("prerequisite_map", {})

    all_topics = {t.get("title", "") for t in topics}
    topics_with_prereqs = set(prerequisite_map.keys())
    all_mentioned: Set[str] = set()

    for prereqs in prerequisite_map.values():
        all_mentioned.update(prereqs)

    # Check for circular references
    circular_refs = await _detect_circular_prereqs(topics, prerequisite_map)

    # Find orphans
    orphans = list(all_topics - topics_with_prereqs - all_mentioned)

    # Check unreachable (simplified)
    first_topic = topics[0].get("title", "") if topics else ""
    reachable = {first_topic}
    to_visit = [first_topic]

    while to_visit:
        current = to_visit.pop()
        for next_topic, prereqs in prerequisite_map.items():
            if current in prereqs and next_topic not in reachable:
                reachable.add(next_topic)
                to_visit.append(next_topic)

    unreachable = list(all_topics - reachable)

    hierarchy_issues = []
    if circular_refs:
        hierarchy_issues.append(f"Found {len(circular_refs)} circular prerequisite chains")
    if orphans and len(orphans) > 1:
        hierarchy_issues.append(f"Found {len(orphans)} orphaned topics")
    if unreachable:
        hierarchy_issues.append(f"Found {len(unreachable)} unreachable topics")

    result = StructureValidationResult(
        circular_references=circular_refs,
        orphaned_topics=orphans,
        unreachable_topics=unreachable,
        hierarchy_issues=hierarchy_issues,
        total_issues=len(circular_refs) + len(orphans) + len(unreachable),
    )

    return {
        "structure_validation": result,
        "phase": "validate_quiz",
    }


async def validate_quiz_node(state: ValidationState) -> Dict[str, Any]:
    """
    Validate quiz quality using LLM assessment.

    LLM evaluates:
    - Questions are well-formed and clear
    - Questions adequately test topic understanding
    - Answer choices are appropriate (for MCQ)
    - Difficulty distribution is balanced
    """
    llm = get_llm(temperature=0.3)
    topics = state.get("topics", [])
    quiz_questions = state.get("quiz_questions", [])

    if not topics:
        return {
            "quiz_validation": {
                "topics_without_quizzes": [],
                "quiz_coverage": {},
                "difficulty_distribution": {"easy": 0, "medium": 0, "hard": 0},
                "unanswered_questions": [],
                "total_issues": 1,
            },
            "phase": "calculate_readiness",
            "errors": ["No topics to validate"],
        }

    # Prepare quiz summary for LLM
    quiz_summary = []
    topic_question_counts: Dict[str, int] = {}
    difficulty_dist = {"easy": 0, "medium": 0, "hard": 0}

    for q in quiz_questions[:10]:  # Limit for token efficiency
        quiz_summary.append({
            "topic": q.get("topic_title", ""),
            "question": q.get("question_text", "")[:100],
            "type": q.get("question_type", ""),
            "difficulty": q.get("difficulty", "medium"),
            "has_answer": bool(q.get("correct_answer")),
        })
        topic = q.get("topic_title", "")
        topic_question_counts[topic] = topic_question_counts.get(topic, 0) + 1
        diff = q.get("difficulty", "medium")
        if diff in difficulty_dist:
            difficulty_dist[diff] += 1

    topics_list = [t.get("title", "") for t in topics]

    # LLM-based quiz validation
    validation_prompt = f"""You are a quiz quality validator. Analyze the quiz questions for the course.

Course: {state.get('course_title', 'Unknown')}
Topics to cover: {', '.join(topics_list)}

Sample Questions:
{json.dumps(quiz_summary, indent=2)}

Difficulty Distribution: {difficulty_dist}

Analyze:
1. **Coverage**: Does each topic have adequate questions? (Minimum 3 per topic)
2. **Quality**: Are questions clear, unambiguous, and well-formed?
3. **Difficulty**: Is there a good mix of easy, medium, and hard questions?
4. **Answerability**: Can questions be answered from course content?

Return JSON:
{{
  "topics_without_quizzes": ["Topic names with < 3 questions"],
  "quiz_coverage": {{"Topic": question_count}},
  "quality_issues": ["List of question quality problems"],
  "unanswered_questions": ["Questions with missing/invalid answers"],
  "difficulty_balance": "good/fair/poor",
  "total_issues": count
}}
"""

    try:
        response = await llm.ainvoke(validation_prompt)
        content = response.content

        # Parse JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result_data = json.loads(content.strip())

        # Build full coverage map
        quiz_coverage = {}
        for topic in topics_list:
            quiz_coverage[topic] = topic_question_counts.get(topic, 0)

        result = {
            "topics_without_quizzes": result_data.get("topics_without_quizzes", []),
            "quiz_coverage": {**quiz_coverage, **result_data.get("quiz_coverage", {})},
            "difficulty_distribution": difficulty_dist,
            "unanswered_questions": result_data.get("unanswered_questions", []),
            "total_issues": result_data.get("total_issues", 0),
            "quality_assessment": result_data.get("difficulty_balance", "fair"),
        }

        return {
            "quiz_validation": result,
            "phase": "calculate_readiness",
        }

    except Exception as e:
        logger.error(f"LLM quiz validation failed: {e}")
        return await _fallback_quiz_validation(state)


async def _fallback_quiz_validation(state: ValidationState) -> Dict[str, Any]:
    """Fallback rule-based quiz validation."""
    topics = state.get("topics", [])
    quiz_questions = state.get("quiz_questions", [])

    topics_without_quizzes: List[str] = []
    quiz_coverage: Dict[str, int] = {}
    difficulty_distribution: Dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    unanswered_questions: List[str] = []

    topic_question_counts: Dict[str, int] = {}
    for q in quiz_questions:
        topic_title = q.get("topic_title", "")
        if topic_title:
            topic_question_counts[topic_title] = topic_question_counts.get(topic_title, 0) + 1
            difficulty = q.get("difficulty", "medium")
            if difficulty in difficulty_distribution:
                difficulty_distribution[difficulty] += 1

    for topic in topics:
        topic_title = topic.get("title", "")
        count = topic_question_counts.get(topic_title, 0)
        quiz_coverage[topic_title] = count
        if count < 3:
            topics_without_quizzes.append(topic_title)

    for q in quiz_questions:
        if not q.get("correct_answer"):
            unanswered_questions.append(q.get("question_text", "")[:50])

    return {
        "quiz_validation": {
            "topics_without_quizzes": topics_without_quizzes,
            "quiz_coverage": quiz_coverage,
            "difficulty_distribution": difficulty_distribution,
            "unanswered_questions": unanswered_questions,
            "total_issues": len(topics_without_quizzes) + len(unanswered_questions),
        },
        "phase": "calculate_readiness",
    }


async def calculate_readiness_node(state: ValidationState) -> Dict[str, Any]:
    """
    Calculate overall readiness score using LLM assessment.

    Combines all validation results and uses LLM to determine
    course readiness with intelligent recommendations.
    """
    llm = get_llm(temperature=0.3)

    content_validation = state.get("content_validation") or {
        "topics_without_content": [],
        "content_coverage": {},
        "empty_topics": [],
        "total_issues": 0,
    }
    structure_validation = state.get("structure_validation") or {
        "circular_references": [],
        "orphaned_topics": [],
        "unreachable_topics": [],
        "hierarchy_issues": [],
        "total_issues": 0,
    }
    quiz_validation = state.get("quiz_validation") or {
        "topics_without_quizzes": [],
        "quiz_coverage": {},
        "difficulty_distribution": {},
        "unanswered_questions": [],
        "total_issues": 0,
    }

    # Prepare validation summary for LLM
    validation_summary = {
        "content": {
            "issues": content_validation.get("total_issues", 0),
            "topics_without_content": len(content_validation.get("topics_without_content", [])),
            "empty_topics": len(content_validation.get("empty_topics", [])),
        },
        "structure": {
            "issues": structure_validation.get("total_issues", 0),
            "circular_references": len(structure_validation.get("circular_references", [])),
            "unreachable_topics": len(structure_validation.get("unreachable_topics", [])),
        },
        "quiz": {
            "issues": quiz_validation.get("total_issues", 0),
            "topics_without_quizzes": len(quiz_validation.get("topics_without_quizzes", [])),
            "difficulty_distribution": quiz_validation.get("difficulty_distribution", {}),
        },
        "totals": {
            "topics": len(state.get("topics", [])),
            "questions": len(state.get("quiz_questions", [])),
            "chunks": len(state.get("content_chunks", [])),
        }
    }

    # LLM-based readiness assessment
    assessment_prompt = f"""You are a course readiness evaluator. Assess the overall quality and readiness of this course.

Course: {state.get('course_title', 'Unknown')}

Validation Results:
{json.dumps(validation_summary, indent=2)}

Evaluate:
1. **Readiness Score** (0.0-1.0): How ready is this course for students?
2. **Critical Issues**: What MUST be fixed before publishing?
3. **Recommendations**: What improvements would enhance the course?

Return JSON:
{{
  "readiness_score": 0.0-1.0,
  "is_valid": true/false,
  "errors": ["Critical issues that must be fixed"],
  "warnings": ["Minor issues to address"],
  "recommendations": ["Specific improvement suggestions"],
  "verdict": "READY FOR PUBLISHING / NEEDS IMPROVEMENT / NOT READY"
}}
"""

    try:
        response = await llm.ainvoke(assessment_prompt)
        content = response.content

        # Parse JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        assessment = json.loads(content.strip())

        result = ValidationResult(
            is_valid=assessment.get("is_valid", False),
            readiness_score=assessment.get("readiness_score", 0.0),
            errors=assessment.get("errors", []),
            warnings=assessment.get("warnings", []),
            info=[],
            content_validation=content_validation,
            structure_validation=structure_validation,
            quiz_validation=quiz_validation,
            recommendations=assessment.get("recommendations", []),
        )

        return {
            "final_result": result,
            "phase": "generate_report",
        }

    except Exception as e:
        logger.error(f"LLM readiness assessment failed: {e}")
        return await _fallback_readiness_calculation(state)


async def _fallback_readiness_calculation(state: ValidationState) -> Dict[str, Any]:
    """Fallback rule-based readiness calculation."""
    content_validation = state.get("content_validation") or {
        "topics_without_content": [],
        "content_coverage": {},
        "empty_topics": [],
        "total_issues": 0,
    }
    structure_validation = state.get("structure_validation") or {
        "circular_references": [],
        "orphaned_topics": [],
        "unreachable_topics": [],
        "hierarchy_issues": [],
        "total_issues": 0,
    }
    quiz_validation = state.get("quiz_validation") or {
        "topics_without_quizzes": [],
        "quiz_coverage": {},
        "difficulty_distribution": {},
        "unanswered_questions": [],
        "total_issues": 0,
    }

    errors: List[str] = []
    warnings: List[str] = []

    # Content validation
    if content_validation.get("topics_without_content"):
        errors.append(f"{len(content_validation.get('topics_without_content', []))} topics have no content")
    if content_validation.get("empty_topics"):
        warnings.append(f"{len(content_validation.get('empty_topics', []))} topics are empty")

    # Structure validation
    if structure_validation.get("circular_references"):
        errors.append(f"{len(structure_validation.get('circular_references', []))} circular prerequisite chains detected")
    if structure_validation.get("unreachable_topics"):
        errors.append(f"{len(structure_validation.get('unreachable_topics', []))} topics are unreachable")

    # Quiz validation
    if quiz_validation.get("topics_without_quizzes"):
        errors.append(f"{len(quiz_validation.get('topics_without_quizzes', []))} topics have no quiz questions")

    # Calculate score
    total_topics = len(state.get("topics", []))
    total_questions = len(state.get("quiz_questions", []))
    total_chunks = len(state.get("content_chunks", []))

    score = 1.0
    score -= min(0.5, 0.1 * len(errors))
    score -= min(0.3, 0.05 * len(warnings))

    if total_questions >= total_topics * 3:
        score += 0.05
    if total_chunks >= total_topics * 5:
        score += 0.05

    score = max(0.0, min(1.0, score))

    recommendations = []
    if errors:
        recommendations.append("Address all critical errors before publishing")
    if warnings:
        recommendations.append("Review warnings and fix if possible")
    if score < 0.8:
        recommendations.append("Add more content and quiz questions to improve readiness")

    result = ValidationResult(
        is_valid=score >= 0.8 and len(errors) == 0,
        readiness_score=score,
        errors=errors,
        warnings=warnings,
        info=[],
        content_validation=content_validation,
        structure_validation=structure_validation,
        quiz_validation=quiz_validation,
        recommendations=recommendations,
    )

    return {
        "final_result": result,
        "phase": "generate_report",
    }


async def generate_report_node(state: ValidationState) -> Dict[str, Any]:
    """
    Generate the final validation report using LLM.

    Creates a comprehensive, human-readable validation report.
    """
    llm = get_llm(temperature=0.5)
    final_result = state.get("final_result")

    if not final_result:
        return {
            "errors": ["No validation result available"],
            "validation_complete": True,
        }

    score = final_result.get("readiness_score", 0.0)
    is_valid = final_result.get("is_valid", False)
    errors = final_result.get("errors", [])
    warnings = final_result.get("warnings", [])
    recommendations = final_result.get("recommendations", [])

    if not final_result:
        return {
            "errors": ["No validation result available"],
            "validation_complete": True,
        }

    score = final_result.get("readiness_score", 0.0)
    is_valid = final_result.get("is_valid", False)
    errors = final_result.get("errors", [])
    warnings = final_result.get("warnings", [])
    recommendations = final_result.get("recommendations", [])

    # Generate LLM-based report
    report_prompt = f"""Generate a clear, professional validation report for a course.

Course: {state.get('course_title', 'Unknown')}
Readiness Score: {score:.2f}/1.0
Validation Status: {'PASSED' if is_valid else 'FAILED'}

Errors Found: {len(errors)}
Warnings: {len(warnings)}

Errors: {errors[:5]}  # First 5 errors
Warnings: {warnings[:5]}  # First 5 warnings
Recommendations: {recommendations[:5]}  # First 5 recommendations

Create a concise report with:
1. Executive summary (1-2 sentences)
2. Key findings (bulleted list)
3. Action items (if any)
4. Final verdict

Keep it professional and actionable.
"""

    try:
        response = await llm.ainvoke(report_prompt)
        llm_report = response.content.strip()
    except:
        llm_report = None

    # Determine status
    if is_valid and score >= 0.9:
        status = "EXCELLENT - Ready to publish"
        ready_status = "READY"
    elif is_valid:
        status = "GOOD - Ready to publish with minor recommendations"
        ready_status = "READY"
    else:
        status = "NEEDS FIXES - Not ready for publishing"
        ready_status = "NOT READY"

    # Format recommendations
    if recommendations:
        recommendations_section = "\n\n### Recommendations:\n" + "\n".join(f"- {r}" for r in recommendations)
    else:
        recommendations_section = ""

    # Use LLM report if available, otherwise use template
    if llm_report:
        message = f"""# Course Validation Report

## {state.get('course_title', 'Unknown')}

{llm_report}

---
{COMPLETION_MESSAGE.format(
    status=status,
    readiness_score=f"{score:.2f}",
    content_status="PASS" if not final_result.get("content_validation", {}).get("total_issues") else "NEEDS ATTENTION",
    structure_status="PASS" if not final_result.get("structure_validation", {}).get("total_issues") else "NEEDS ATTENTION",
    quiz_status="PASS" if not final_result.get("quiz_validation", {}).get("total_issues") else "NEEDS ATTENTION",
    error_count=len(errors),
    warning_count=len(warnings),
    recommendations_section=recommendations_section,
    ready_status=ready_status,
)}"""
    else:
        message = COMPLETION_MESSAGE.format(
            status=status,
            readiness_score=f"{score:.2f}",
            content_status="PASS" if not final_result.get("content_validation", {}).get("total_issues") else "NEEDS ATTENTION",
            structure_status="PASS" if not final_result.get("structure_validation", {}).get("total_issues") else "NEEDS ATTENTION",
            quiz_status="PASS" if not final_result.get("quiz_validation", {}).get("total_issues") else "NEEDS ATTENTION",
            error_count=len(errors),
            warning_count=len(warnings),
            recommendations_section=recommendations_section,
            ready_status=ready_status,
        )

    return {
        "validation_complete": True,
        "awaiting_fixes": not is_valid,
        "validation_passed": is_valid,
        "readiness_score": score,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "subagent_results": {
            **state.get("subagent_results", {}),
            "validation": {
                "status": "passed" if is_valid else "failed",
                "readiness_score": score,
                "errors": errors,
                "warnings": warnings,
                "report": message,
            }
        },
        "phase": "complete",
    }
