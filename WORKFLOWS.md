# Agentic Tutor - Agent Workflows Documentation

This file documents all agent workflows with detailed node relationships, data flow, and feedback loops. This documentation will be used to generate visual workflow diagrams.

---

# WORKFLOW 1: CONSTRUCTOR (Course Creation)

## Overview

The Constructor workflow enables course creators to build courses from raw materials (PDFs, slides, videos) using coordinated AI agents.

**Entry Point:** Coordinator Agent
**Exit Condition:** Course validated and published
**State Storage:** LangGraph Checkpointer (SQLite)

---

## AGENT 1: COORDINATOR AGENT (Main)

**Purpose:** Orchestrates the entire course construction process

**File:** `backend/app/agents/constructor/coordinator/agent.py`

### State: ConstructorState

```
ConstructorState:
  messages: List[BaseMessage]          # Conversation history
  session_id: str                       # Unique session ID
  creator_id: int                       # Creator's user ID
  course_id: Optional[int]              # Course ID (assigned after creation)
  course_info: CourseInfo               # {title, description, difficulty, tags}
  phase: str                            # Current construction phase
  uploaded_files: List[UploadedFile]    # Files awaiting processing
  processed_files: List[UploadedFile]   # Files successfully processed
  units: List[UnitInfo]                 # Course units
  topics: List[TopicInfo]               # Course topics
  quiz_questions: List[QuizQuestionInfo] # Generated quiz questions
  current_agent: str                    # Currently active sub-agent
  pending_subagent: Optional[str]       # Next sub-agent to dispatch
  subagent_results: Dict[str, Any]      # Results from sub-agents
  content_chunks: List[Dict]            # Chunks from ingestion
  progress: float                       # 0.0 to 1.0
  validation_passed: bool               # Final validation status
  readiness_score: float                # 0.0 to 1.0
  errors: List[str]                     # Error list
```

### Nodes and Edges

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           COORDINATOR AGENT                                 │
│                                                                              │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐           │
│  │ welcome_creator│───►│collect_course  │───►│check_completion│           │
│  │      NODE      │    │     _info      │    │     NODE       │           │
│  └────────────────┘    └────────────────┘    └────────┬───────┘           │
│                                                      │                     │
│                                    ┌─────────────────┴──────────────────┐  │
│                                    │ MORE INFO NEEDED?                  │  │
│                                    │   Yes → collect_course_info       │  │
│                                    │   No  → route_to_subagent         │  │
│                                    └───────────────────────────────────┘  │
│                                                              │             │
│                       ┌──────────────────────────────────────┼──────────┐ │
│                       │                                      │          │ │
│                       ▼                                      ▼          │ │
│  ┌────────────────┐                            ┌────────────────┐          │ │
│  │ handle_upload   │                            │dispatch_       │          │ │
│  │     NODE        │                            │  ingestion     │          │ │
│  └────────┬───────┘                            │    NODE        │          │ │
│           │                                     └───────┬────────┘          │ │
│           │                                             │                   │ │
│           │                                     ┌───────┴──────────────────┐ │
│           │                                     │ INGESTION COMPLETE?     │ │
│           │                                     │ Returns: processed_files│ │ │
│           │                                     │         content_chunks  │ │ │
│           │                                     └──────────────────────────┘ │
│           │                                             │                   │
│           ▼                                             ▼                   │
│  ┌────────────────┐                            ┌────────────────┐          │ │
│  │dispatch_       │                            │dispatch_       │          │ │
│  │structure       │                            │  quiz          │          │ │
│  │    NODE        │                            │    NODE        │          │ │
│  └────────┬───────┘                            └───────┬────────┘          │ │
│           │                                             │                   │
│           │                                     ┌───────┴──────────────────┐ │
│           │                                     │ QUIZ GENERATION         │ │
│           │                                     │ COMPLETE?               │ │
│           │                                     │ Returns: quiz_questions │ │ │
│           │                                     └──────────────────────────┘ │
│           │                                             │                   │
│           ▼                                             ▼                   │
│  ┌────────────────┐                            ┌────────────────┐          │ │
│  │dispatch_       │                            │dispatch_       │          │ │
│  │validation      │                            │finalize_course │          │ │
│  │    NODE        │                            │     NODE       │          │ │
│  └────────┬───────┘                            └───────┬────────┘          │ │
│           │                                             │                   │
│           │                                     ┌───────┴──────────────────┐ │
│           │                                     │ VALIDATION PASSED?      │ │
│           │                                     │ Returns: valid=True/    │ │ │
│           │                                     │         False, errors    │ │ │
│           │                                     └──────────────────────────┘ │
│           │                                                      │          │
│           └──────────────────────────────────────────────────────┼──────────┘ │
│                                                                  │             │
│                                                         ┌────────┴────────┐   │
│                                                         │ publish_course  │   │
│                                                         │     NODE        │   │
│                                                         └─────────────────┘   │
│                                                                  │             │
│                                                                  ▼             │
│                                                             ┌─────────┐      │
│                                                             │   END   │      │
│                                                             └─────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Sub-Agent Dispatch Flow

```
Coordinator State → Sub-Agent Invoked → Sub-Agent Processes → Returns Result → Coordinator Integrates Result
```

**Feedback Loops:**
1. **Validation Feedback Loop:** If validation fails, Coordinator receives errors → updates state → can re-dispatch to Validation after fixes
2. **Creator Feedback Loop:** At any phase, Creator can provide feedback → Coordinator updates state → re-dispatches to appropriate sub-agent

---

## AGENT 2: INGESTION AGENT (Sub-Agent)

**Purpose:** Parse uploaded files and extract content

**File:** `backend/app/agents/constructor/ingestion/agent.py`

### State: IngestionState (shares ConstructorState)

```
IngestionState (ConstructorState subset):
  course_id: str
  uploaded_files: List[UploadedFile]
  processed_files: List[UploadedFile]
  extracted_contents: List[ExtractionResult]
  content_chunks: List[TextChunk]
  subagent_results: Dict
  errors: List[str]
```

### Nodes and Edges

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            INGESTION AGENT                                  │
│                                                                              │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│    │detect_types  │───►│  extract     │───►│   chunk      │              │
│    │    NODE      │    │    NODE      │    │    NODE      │              │
│    │              │    │              │    │              │              │
│    │Groups files  │    │Calls:        │    │Calls:        │              │
│    │by type       │    │- ingest_pdf  │    │- chunk_by_   │              │
│    │              │    │- ingest_ppt  │    │  semantic    │              │
│    │Returns:      │    │- ingest_docx │    │              │              │
│    │files_by_type │    │- ingest_video│    │Returns:      │              │
│    └──────────────┘    │Returns:      │    │content_chunks│              │
│                        │extracted_    │    └──────┬───────┘              │
│                        │contents      │           │                        │
│                        └──────┬───────┘           │                        │
│                               │                    │                        │
│                               ▼                    ▼                        │
│                        ┌──────────────┐    ┌──────────────┐              │
│                        │   store      │    │   report     │              │
│                        │   NODE       │    │   NODE       │              │
│                        │              │    │              │              │
│                        │Calls:        │    │Summarizes:   │              │
│                        │- generate_   │    │- files_      │              │
│                        │  embeddings  │    │  processed   │              │
│                        │- store_in_   │    │- chunks_     │              │
│                        │  vector_db   │    │  created     │              │
│                        │              │    │              │              │
│                        │Returns:      │    │Returns:      │              │
│                        │vector_ids    │    │completion_   │              │
│                        │              │    │msg           │              │
│                        └──────┬───────┘    └──────┬───────┘              │
│                               │                    │                        │
│                               └────────────────────┘                        │
│                                                  │                         │
│                                                  ▼                         │
│                                             ┌─────────┐                   │
│                                             │   END   │                   │
│                                             └─────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tool Calls

| Node | Tool | Purpose |
|------|------|---------|
| extract | `ingest_pdf` | Parse PDF, extract text/pages |
| extract | `ingest_ppt` | Parse PowerPoint, extract slides |
| extract | `ingest_docx` | Parse Word documents |
| extract | `ingest_video` | Extract transcript/metadata |
| chunk | `chunk_content_by_semantic` | Split content by semantic boundaries |
| store | `generate_embeddings_for_chunks` | Create vector embeddings |
| store | `store_in_vector_db` | Store in course vector DB |

### Data Returned to Coordinator

```python
subagent_results = {
    "ingestion": {
        "files_by_type": {"pdf": 5, "ppt": 2, ...},
        "total_pending": 7,
        "status": "completed",
        "summary": {
            "files_processed": 7,
            "files_failed": 0,
            "total_chunks_created": 156
        }
    }
}
```

---

## AGENT 3: STRUCTURE ANALYSIS AGENT (Sub-Agent)

**Purpose:** Analyze content to detect topics, organize structure, link prerequisites

**File:** `backend/app/agents/constructor/structure/agent.py`

### State: StructureState

```
StructureState:
  course_id: str
  course_title: str
  content_chunks: List[Dict]
  phase: str                            # "analyze_content" → "finalize"
  detected_topics: List[DetectedTopic]   # Topics extracted from content
  total_topics: int
  detected_units: List[DetectedUnit]     # Units grouping topics
  total_units: int
  topic_relationships: List[TopicRelationship]
  prerequisite_map: Dict                 # topic → prereqs
  structure_hierarchy: Dict              # Final structure
  topics_by_unit: Dict                   # unit → topics
  confidence_scores: Dict
  errors: List[str]
  warnings: List[str]
  analysis_complete: bool
```

### Nodes and Edges

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STRUCTURE ANALYSIS AGENT                             │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │analyze_      │───►│detect_topics │───►│group_into_   │                  │
│  │content       │    │    NODE      │    │  units       │                  │
│  │NODE          │    │              │    │   NODE       │                  │
│  │              │    │Calls:        │    │              │                  │
│  │Validates     │    │detect_topics │    │Calls:        │                  │
│  │input chunks  │    │_from_chunks  │    │organize_     │                  │
│  │              │    │              │    │chunks_into_  │                  │
│  │Returns:      │    │Returns:      │    │  units       │                  │
│  │phase update  │    │detected_     │    │              │                  │
│  │              │    │topics        │    │Returns:      │                  │
│  └──────────────┘    │confidence_   │    │detected_     │                  │
│                      │scores        │    │units         │                  │
│                      └──────┬───────┘    │topics_by_    │                  │
│                             │             │  unit        │                  │
│                             ▼             └──────┬───────┘                  │
│                      ┌──────────────┐            │                          │
│                      │identify_     │            │                          │
│                      │prerequisites │            │                          │
│                      │    NODE      │            │                          │
│                      │              │            │                          │
│                      │Calls:        │            │                          │
│                      │identify_     │            │                          │
│                      │prerequisite_ │            │                          │
│                      │relationships │            │                          │
│                      │              │            │                          │
│                      │Returns:      │            │                          │
│                      │topic_        │            │                          │
│                      │relationships │            │                          │
│                      │prerequisite_  │            │                          │
│                      │map           │            │                          │
│                      └──────┬───────┘            │                          │
│                             │                    │                          │
│                             ▼                    ▼                          │
│                      ┌──────────────┐    ┌──────────────┐                  │
│                      │build_        │───►│validate_    │                  │
│                      │hierarchy     │    │structure    │                  │
│                      │    NODE       │    │    NODE      │                  │
│                      │              │    │              │                  │
│                      │Combines all  │    │Checks:       │                  │
│                      │into final    │    │- Circular    │                  │
│                      │structure     │    │  deps        │                  │
│                      │              │    │- Orphans     │                  │
│                      │Returns:      │    │- Unreachable │                  │
│                      │structure_    │    │              │                  │
│                      │hierarchy     │    │Returns:      │                  │
│                      └──────┬───────┘    │errors,       │                  │
│                             │             │warnings      │                  │
│                             │             │quality_score │                  │
│                             ▼             └──────┬───────┘                  │
│                      ┌──────────────┐            │                          │
│                      │suggest_      │            │                          │
│                      │organization  │            │                          │
│                      │    NODE       │            │                          │
│                      │              │            │                          │
│                      │Presents to   │            │                          │
│                      │creator for   │            │                          │
│                      │review        │            │                          │
│                      │              │            │                          │
│                      │Returns:      │            │                          │
│                      │awaiting_     │            │                          │
│                      │approval=True │            │                          │
│                      └──────┬───────┘            │                          │
│                             │                    │                          │
│                             ▼                    │                          │
│                      ┌──────────────┐            │                          │
│                      │finalize_     │            │                          │
│                      │structure     │            │                          │
│                      │    NODE       │            │                          │
│                      │              │            │                          │
│                      │Converts to   │            │                          │
│                      │DB format     │            │                          │
│                      │(UnitInfo,    │            │                          │
│                      │ TopicInfo)   │            │                          │
│                      └──────┬───────┘            │                          │
│                             │                    │                          │
│                             ▼                    │                          │
│                        ┌─────────┐              │                          │
│                        │   END   │              │                          │
│                        └─────────┘              │                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tool Calls

| Node | Tool | Purpose |
|------|------|---------|
| detect_topics | `detect_topics_from_chunks` | LLM-based topic detection |
| group_into_units | `organize_chunks_into_units` | Group topics into logical units |
| identify_prerequisites | `identify_prerequisite_relationships` | Find prerequisite relationships |

### Data Returned to Coordinator

```python
subagent_results = {
    "structure": {
        "status": "completed",
        "units": [...],           # UnitInfo list
        "topics": [...],          # TopicInfo list
        "quality_score": 0.92,
        "summary": {...}
    }
}
```

---

## AGENT 4: QUIZ GENERATION AGENT (Sub-Agent)

**Purpose:** Create quiz questions for each topic

**File:** `backend/app/agents/constructor/quiz_gen/agent.py`

### State: QuizGenState

```
QuizGenState:
  course_id: str
  course_title: str
  topics: List[Dict]                     # Topics from structure agent
  content_chunks: List[Dict]
  target_questions_per_topic: int
  question_types: List[str]              # ["multiple_choice", "true_false", "short_answer"]
  difficulty_levels: List[str]           # ["easy", "medium", "hard"]
  phase: str                             # "plan" → "finalize"
  current_topic_index: int
  current_topic: Dict
  topic_quizzes: List[TopicQuizResult]
  all_questions: List[GeneratedQuestion]
  total_questions_generated: int
  questions_by_type: Dict
  questions_by_difficulty: Dict
  validation_errors: List[str]
  rubrics: Dict
  topics_completed: int
  topics_total: int
  generation_complete: bool
```

### Nodes and Edges

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          QUIZ GENERATION AGENT                              │
│                                                                              │
│  ┌──────────────┐                                                            │
│  │plan_quiz_    │                                                            │
│  │generation    │                                                            │
│  │    NODE      │                                                            │
│  │              │                                                            │
│  │Plans Q count │                                                            │
│  │& distribution│                                                            │
│  │per topic     │                                                            │
│  └──────┬───────┘                                                            │
│         │                                                                    │
│         ▼                                                                    │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │select_topic  │───►│generate_     │───►│validate_     │                  │
│  │    NODE      │    │questions     │    │questions     │                  │
│  │              │    │    NODE       │    │    NODE       │                  │
│  │Gets next     │    │              │    │              │                  │
│  │topic to      │    │For each type: │    │Checks:       │                  │
│  │process       │    │- MCQ         │    │- Answerable? │                  │
│  │              │    │- True/False  │    │- Clear?      │                  │
│  │Returns:      │    │- Short Answer│    │- Correct?    │                  │
│  │current_topic │    │              │    │- Quality OK? │                  │
│  │              │    │Calls:        │    │              │                  │
│  │OR           │    │- generate_   │    │Returns:      │                  │
│  │generation_   │    │  multiple_   │    │validation_   │                  │
│  │complete=True │    │  choice      │    │passed        │                  │
│  └──────┬───────┘    │- generate_   │    └──────┬───────┘                  │
│         │            │  true_false  │           │                            │
│         │            │- generate_   │           ▼                            │
│         │            │  short_      │    ┌──────────────┐                  │
│         │            │  answer      │    │create_       │                  │
│         │            │              │    │rubrics       │                  │
│         │            │Returns:      │    │    NODE       │                  │
│         │            │generated_    │    │              │                  │
│         │            │questions     │    │For short     │                  │
│         │            │              │    │answer only   │                  │
│         │            │              │    │              │                  │
│         │            │              │    │Calls:        │                  │
│         │            │              │    │create_quiz_  │                  │
│         │            │              │    │  rubric      │                  │
│         │            │              │    │              │                  │
│         │            │              │    │Returns:      │                  │
│         │            │              │    │rubrics       │                  │
│         │            │              │    └──────┬───────┘                  │
│         │            │              │           │                            │
│         │            │              └───────────┼────────────────────────────┘
│         │            │                          │
│         │            └──────────────────────────┼────────────────────────────┐
│         │                                       │                            │
│         ▼                                       ▼                            │
│  ┌──────────────┐                    ┌──────────────┐                      │
│  │check_        │◄───────────────────│finalize_quiz │                      │
│  │completion    │                    │    _bank     │                      │
│  │    NODE       │                    │    NODE      │                      │
│  │              │                    │              │                      │
│  │More topics?  │                    │Converts to   │                      │
│  │ Yes → select_ │                    │DB format     │                      │
│  │       topic   │                    │(QuizQuestion │                      │
│  │ No  → finalize│                    │ Info)        │                      │
│  └──────────────┘                    └──────┬───────┘                      │
│                                             │                              │
│                                             ▼                              │
│                                          ┌─────────┐                        │
│                                          │   END   │                        │
│                                          └─────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tool Calls

| Node | Tool | Purpose |
|------|------|---------|
| generate_questions | `generate_multiple_choice` | Generate MCQ questions |
| generate_questions | `generate_true_false` | Generate T/F questions |
| generate_questions | `generate_short_answer` | Generate short answer questions |
| create_rubrics | `create_quiz_rubric` | Create grading rubrics |

### Loop Logic

```
FOR each topic IN topics:
    select_topic → generate_questions → validate_questions → create_rubrics → check_completion
    IF more topics:
        → select_topic (LOOP)
    ELSE:
        → finalize_quiz_bank
```

### Data Returned to Coordinator

```python
subagent_results = {
    "quiz": {
        "status": "completed",
        "total_questions": 47,
        "questions_by_type": {"multiple_choice": 28, "true_false": 12, "short_answer": 7},
        "questions_by_difficulty": {"easy": 14, "medium": 24, "hard": 9}
    }
}
```

---

## CONSTRUCTOR WORKFLOW: COMPLETE FLOW

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  CREATOR    │────►│COORDINATOR  │────►│INGESTION    │────►│  STRUCTURE  │
│  (Human)    │     │  AGENT      │     │   AGENT     │     │   AGENT     │
│             │     │             │     │             │     │             │
│ Uploads     │     │ Orchestrates│     │ Parses files│     │ Detects     │
│ materials   │     │ workflow    │     │ Extracts    │     │ topics      │
│ Provides    │     │ Collects    │     │ Chunks      │     │ Organizes   │
│ course info │     │ info        │     │ Stores in   │     │ units       │
│             │     │             │     │ Vector DB   │     │ Links prereqs│
└─────────────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
                          │                   │                   │
                          │◄───────────────────┴───────────────────┤          │
                          │     Returns to Coordinator           │          │
                          │     with results                     │          │
                          │                                     │          │
                          ▼                                     │          │
                   ┌─────────────┐                                │          │
                   │   QUIZ      │◄───────────────────────────────┘          │
                   │ GENERATION  │                                             │
                   │   AGENT     │                                             │
                   │             │                                             │
                   │ Generates   │                                             │
                   │ questions   │                                             │
                   │ for each    │                                             │
                   │ topic       │                                             │
                   └──────┬──────┘                                             │
                          │                                                    │
                          │◄───────────────────────────────────────────────────┤
                          │     Returns to Coordinator                           │
                          │     with quiz questions                              │
                          │                                                    │
                          ▼                                                    │
                   ┌─────────────┐                                            │
                   │VALIDATION   │                                            │
                   │   AGENT     │                                            │
                   │             │                                            │
                   │ Validates   │                                            │
                   │ completeness│                                            │
                   │ Checks      │                                            │
                   │ structure   │                                            │
                   │ Validates   │                                            │
                   │ quizzes     │                                            │
                   └──────┬──────┘                                            │
                          │                                                    │
                          │◄───────────────────────────────────────────────────┤
                          │     Returns validation result                       │
                          │     If valid: publish                              │
                          │     If invalid: show errors, allow fixes            │
                          │                                                    │
                          ▼                                                    │
                   ┌─────────────┐                                            │
                   │  PUBLISH    │                                            │
                   │   COURSE    │                                            │
                   └─────────────┘                                            │
                          │                                                    │
                          ▼                                                    │
                   ┌─────────────┐                                            │
                   │    END     │                                            │
                   └─────────────┘                                            │
```

---

## AGENT 5: VALIDATION AGENT (Sub-Agent)

**Purpose:** Validates course quality before publishing

**File:** `backend/app/agents/constructor/validation/agent.py`

### State: ValidationState

```
ValidationState:
  course_id: str
  course_title: str
  units: List[Dict]                     # From structure agent
  topics: List[Dict]                    # From structure agent
  content_chunks: List[Dict]            # From ingestion agent
  quiz_questions: List[Dict]            # From quiz agent
  prerequisite_map: Dict                 # From structure agent
  phase: str                             # "validate_content" → "generate_report"
  content_validation: ContentValidationResult
  structure_validation: StructureValidationResult
  quiz_validation: QuizValidationResult
  final_result: ValidationResult
  validation_complete: bool
  awaiting_fixes: bool
```

### Nodes and Edges

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            VALIDATION AGENT                                │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │validate_     │───►│validate_     │───►│validate_     │                  │
│  │  content     │    │  structure   │    │    quiz      │                  │
│  │    NODE      │    │    NODE      │    │    NODE      │                  │
│  │              │    │              │    │              │                  │
│  │Checks:       │    │Checks:       │    │Checks:       │                  │
│  │- Every topic │    │- Circular    │    │- Every topic │                  │
│  │  has content │    │  prereqs     │    │  has >=3    │                  │
│  │- No empty    │    │- Orphaned    │    │  questions   │                  │
│  │  topics      │    │  topics      │    │- Difficulty  │                  │
│  │              │    │- Unreachable │    │  distribution│                  │
│  │Returns:      │    │  topics      │    │- Question    │                  │
│  │content_      │    │              │    │  formatting  │                  │
│  │validation    │    │Returns:      │    │              │                  │
│  │              │    │structure_    │    │Returns:      │                  │
│  │              │    │validation    │    │quiz_         │                  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                  │
│         │                   │                   │                          │
│         └───────────────────┴───────────────────┼──────────────────────────┘
│                                                 │                          │
│                                                 ▼                          │
│                                      ┌──────────────┐                    │
│                                      │calculate_    │                    │
│                                      │readiness     │                    │
│                                      │    NODE      │                    │
│                                      │              │                    │
│                                      │Combines all  │                    │
│                                      │validation   │                    │
│                                      │results      │                    │
│                                      │              │                    │
│                                      │Returns:      │                    │
│                                      │readiness_    │                    │
│                                      │score (0-1)  │                    │
│                                      │errors,       │                    │
│                                      │warnings      │                    │
│                                      └──────┬───────┘                    │
│                                             │                            │
│                                             ▼                            │
│                                      ┌──────────────┐                    │
│                                      │generate_     │                    │
│                                      │report        │                    │
│                                      │    NODE      │                    │
│                                      │              │                    │
│                                      │Creates final │                    │
│                                      │validation   │                    │
│                                      │report with  │                    │
│                                      │recommend.   │                    │
│                                      └──────┬───────┘                    │
│                                             │                            │
│                                             ▼                            │
│                                          ┌─────────┐                      │
│                                          │   END   │                      │
│                                          └─────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Validation Criteria

| Category | Checks | Pass Condition |
|----------|--------|---------------|
| Content | Every topic has materials, no empty topics | 0 critical issues |
| Structure | No circular prereqs, all topics reachable | 0 critical issues |
| Quiz | Every topic has ≥3 questions, mixed difficulty | 0 critical issues |
| Overall | Readiness score ≥ 0.8 | score >= 0.8 |

### Data Returned to Coordinator

```python
subagent_results = {
    "validation": {
        "status": "passed" / "failed",
        "readiness_score": 0.92,
        "errors": ["critical issues"],
        "warnings": ["minor issues"]
    }
}
```

### Feedback Loop

```
If validation fails:
    Validation → Coordinator → Creator (show errors)
    Creator makes fixes → Coordinator → Re-run validation
    Validation passes → Coordinator → Publish course
```

---

## ORCHESTRATION LAYER

**File:** `backend/app/agents/constructor/orchestration.py`

The `ConstructorOrchestrator` class provides the integration between the Coordinator and all sub-agents.

### Orchestrator Methods

| Method | Sub-Agent | Purpose |
|--------|-----------|---------|
| `invoke_ingestion()` | IngestionGraph | Process uploaded files |
| `invoke_structure()` | StructureGraph | Analyze and organize content |
| `invoke_quiz()` | QuizGenGraph | Generate quiz questions |
| `invoke_validation()` | ValidationGraph | Validate course quality |

### Data Flow

```
Coordinator State
       │
       ▼
ConstructorOrchestrator.get_orchestrator()
       │
       ├──► invoke_ingestion(ConstructorState) → Updated ConstructorState
       ├──► invoke_structure(ConstructorState) → Updated ConstructorState
       ├──► invoke_quiz(ConstructorState) → Updated ConstructorState
       └──► invoke_validation(ConstructorState) → Updated ConstructorState
```

### State Transformation

Each orchestrator method:
1. Extracts relevant data from `ConstructorState`
2. Creates the sub-agent's state
3. Invokes the sub-agent graph
4. Extracts results from sub-agent state
5. Returns updates as `ConstructorState` delta

---

# WORKFLOW 2: TUTOR (Student Learning)

## Overview

The Tutor workflow enables students to learn courses through adaptive AI-powered tutoring sessions.

**Entry Point:** Session Coordinator Agent
**Exit Condition:** Session ended (time limit, goal achieved, or student request)
**State Storage:** LangGraph Checkpointer (SQLite) - single file with thread-based isolation

**Key Design Difference:** Unlike Constructor which uses separate sub-agent graphs, Tutor uses a **single graph with conditional routing** to different modes (explainer, gap_analysis, quiz). This is more efficient for real-time student interaction.

---

## AGENT 1: SESSION COORDINATOR AGENT (Main)

**Purpose:** Guides students through adaptive learning sessions, routes to appropriate modes

**File:** `backend/app/agents/tutor/graph.py`

### State: TutorState

```
TutorState:
  # Session
  session_id: str
  student_id: int
  course_id: int

  # Conversation
  messages: Annotated[List[Dict], add_messages]

  # Learning state
  current_topic: Optional[TopicInfo]
  current_unit: Optional[UnitInfo]
  mastery_snapshot: Dict[int, float]     # topic_id -> mastery (0-1)

  # Session progress
  session_goal: Optional[str]
  topics_covered: List[int]              # topic_ids covered this session
  interactions_count: int

  # Decision state
  current_mode: str                       # "welcome" | "explainer" | "gap_analysis" | "quiz" | "review" | "end"
  next_action: str
  action_rationale: str

  # Student context (cached)
  student_context: Optional[StudentContext]

  # Knowledge gaps
  identified_gaps: List[GapInfo]
  weak_topics: List[int]                  # topic_ids with mastery < 0.5

  # Spaced repetition
  topics_due_for_review: List[int]        # topic_ids not reviewed in 7+ days

  # Quiz state (hard-coded assessment, NO LLM)
  current_quiz: Optional[Dict]
  quiz_position: int
  quiz_score: float
  quiz_start_time: Optional[str]
  quiz_completed: bool

  # Explanation state
  explanation_given: Optional[str]
  examples_used: List[str]

  # Navigation state
  current_content_position: Optional[str]  # "video_123", "topic_45", etc.
  content_progress: Dict[str, float]       # content_id -> progress (0-1)

  # Session control
  should_end: bool
  end_reason: Optional[str]
  session_summary: Optional[str]

  # Timestamps
  session_started_at: str
  last_activity_at: str
```

### Nodes and Edges

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SESSION COORDINATOR                               │
│                                                                              │
│  ┌────────────────┐                                                         │
│  │    WELCOME     │  Load mastery snapshot, student context                  │
│  │     NODE       │  Generate personalized welcome message                   │
│  │                │  Identify weak topics and spaced repetition needs       │
│  └────────┬───────┘                                                         │
│           │                                                                 │
│           ▼                                                                 │
│  ┌────────────────┐    ┌─────────────────────────────────────────────────┐ │
│  │    INTAKE      │    │ Process student input, determine next action      │ │
│  │     NODE       │    │                                                  │ │
│  └────────┬───────┘    │ route_by_action():                               │ │
│           │            │  - "quiz" keyword → quiz mode                     │ │
│           │            │  - "help/stuck" → clarify mode (explainer)        │ │
│           │            │  - "review" → review mode (explainer)             │ │
│           │            │  - "gap/weak" → gap_analysis mode                 │ │
│           │            │  - "bye/done" → end session                       │ │
│           │            │  - else → LLM decides based on context            │ │
│           │            └─────────────────────────────────────────────────┘ │
│           │                                                                 │
│           └─────────────┬───────────────────┬──────────────┬────────────┐  │
│                         │                   │              │            │  │
│                         ▼                   ▼              ▼            ▼  │
│              ┌─────────────────┐  ┌─────────────┐  ┌─────────┐  ┌──────────┐│
│              │   EXPLAINER     │  │ GAP_        │  │  QUIZ   │  │SUMMARIZE  ││
│              │     NODE        │  │ ANALYSIS    │  │  NODE   │  │   NODE    ││
│              │                 │  │  NODE       │  │         │  │          ││
│              │Teach new topics │  │Identify     │  │Present  │  │Generate  ││
│              │Review material  │  │knowledge    │  │questions│  │session   ││
│              │Clarify confusion│  │gaps         │  │(hard-   │  │summary   ││
│              │                 │  │Prioritize   │  │coded)   │  │End       ││
│              │Uses RAG for     │  │remediation  │  │         │  │session   ││
│              │content          │  │             │  │         │  │          ││
│              │Adapts to        │  │             │  │         │  │          ││
│              │student state    │  │             │  │         │  │          ││
│              └────────┬────────┘  └──────┬──────┘  └────┬────┘  └────┬─────┘│
│                       │                  │              │             │        │
│                       │         ┌────────┴─────────┐    │             │        │
│                       │         │                  │    │             │        │
│                       │         ▼                  ▼    ▼             │        │
│                       │  ┌─────────────────┐  ┌─────────┐           │        │
│                       │  │ Check every     │  │GRADE_   │           │        │
│                       │  │ 3rd interaction │  │QUIZ     │           │        │
│                       │  └───────┬─────────┘  │NODE     │           │        │
│                       │          │             │(hard-   │           │        │
│                       │          │             │coded)   │           │        │
│                       │          │             └────┬────┘           │        │
│                       │          │                  │                │        │
│                       │          │         ┌────────┴─────────┐      │        │
│                       │          │         ▼                  ▼      │        │
│                       │          │    ┌─────────┐       ┌─────────┐│        │
│                       │          │    │ More    │       │ All     ││        │
│                       │          │    │questions│       │done     ││        │
│                       │          │    └────┬────┘       └────┬────┘│        │
│                       │          │         │                  │     │        │
│                       │          └─────────┴──────────────────┘     │        │
│                       │                                        │        │
│                       └────────────────────────────────────────┘        │
│                                                                │        │
│                                                                ▼        │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │                    should_continue()                        │      │
│  │                                                              │      │
│  │  Checks:                                                     │      │
│  │  - should_end == True? (student requested)                   │      │
│  │  - elapsed_time > 60 minutes? (max session)                  │      │
│  │                                                              │      │
│  │  Returns: "continue" or "end"                                │      │
│  └──────────────────────────────┬───────────────────────────────┘      │
│                                 │                                       │
│                     ┌───────────┴─────────┐                             │
│                     ▼                     ▼                             │
│              ┌─────────────┐         ┌─────────────┐                       │
│              │  continue   │         │     end     │                       │
│              │   (loop)    │         │             │                       │
│              └─────────────┘         └─────────────┘                       │
│                     │                     │                               │
│                     ▼                     ▼                               │
│                ┌─────────┐           ┌─────────┐                            │
│                │ INTAKE  │           │  END    │                            │
│                └─────────┘           └─────────┘                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Mode: Explainer (Teach/Review/Clarify)

**Purpose:** Provide personalized explanations using RAG from course content

**Personality Adaptation:**

| Student State | Personality | Behavior |
|--------------|-------------|----------|
| Struggling (mastery < 0.5, negative sentiment) | Extra Supportive | Simple language, more examples, validates effort |
| Confident (mastery > 0.7, positive sentiment) | Concise & Challenging | Advanced terms, faster pace, deeper questions |
| Bored (low engagement feedback) | Engaging | Interesting analogies, surprising facts |
| Frustrated (negative feedback) | Patient & Reassuring | Acknowledge frustration, break down problems |
| Neutral | Balanced | Clear explanations, appropriate pace |

**Sub-modes:**

1. **Teach Mode:** New topic introduction
   - Retrieves course content via RAG
   - Adapts explanation to student's learning style
   - Provides examples relevant to student interests

2. **Review Mode:** Spaced repetition
   - Topics not reviewed in 7+ days
   - Focuses on key concepts
   - Connects to related topics

3. **Clarify Mode:** Address confusion
   - Uses different approach than before
   - Provides alternative explanations
   - Checks understanding with follow-up question

### Mode: Gap Analysis

**Purpose:** Identify and prioritize knowledge gaps

**Process:**
1. Get mastery snapshot across all topics
2. Identify topics with mastery < 0.5 (threshold)
3. Check prerequisite chains
4. Prioritize based on:
   - Criticality (blocks other learning)
   - Impact (prerequisite for upcoming topics)
   - Student confidence (balance challenging/achievable)
5. Generate remediation plan

**Output:**
```python
identified_gaps = [
    {
        "topic_id": 5,
        "topic_title": "Linear Regression",
        "current_mastery": 0.3,
        "required_mastery": 0.7,
        "priority": "critical",
        "is_prerequisite_for": [7, 8, 9]
    },
    ...
]
```

### Mode: Quiz (Hard-coded Assessment)

**Purpose:** Administer quizzes and grade answers (NO LLM for cost/speed)

**Process:**
1. Select topics (weak_topics or current_topic)
2. Get questions from quiz bank (pre-generated by Constructor)
3. Present question to student
4. Grade answer using string comparison (hard-coded)
5. Record attempt and update mastery
6. Show results with time taken

**Grading (Hard-coded):**

| Question Type | Grading Method |
|--------------|----------------|
| Multiple Choice | Direct string match (A/B/C/D) |
| True/False | Direct string match (true/false) |
| Short Answer | Simple keyword matching |

**Quiz Results Display:**
```
📊 Quiz Results!

You scored: 4/5 (80%)
Time taken: 45 seconds

🎉 Excellent work!

Would you like to:
- Review the topics you missed
- Try another quiz
- Move on to new content
- End the session
```

### Routing Logic

**route_by_action():**
```python
action = state.get("next_action", "teach")

if action in ["teach", "review", "clarify"]:
    return "explainer"
elif action == "gap_analysis":
    return "gap_analysis"
elif action == "quiz":
    return "quiz"
elif action == "summarize":
    return "summarize"
else:
    return "intake"  # Loop for more input
```

**route_after_explainer():**
```python
# Every 3rd interaction, suggest a quiz
if state["interactions_count"] % 3 == 0:
    return "quiz"
else:
    return "intake"
```

**route_after_quiz():**
```python
if not state["quiz_completed"]:
    return "grade"  # Grade current answer
elif more_questions_remaining:
    return "quiz"   # Next question
else:
    return "intake"  # Back to conversation
```

**should_continue():**
```python
if state.get("should_end", False):
    return "end"
elif calculate_time_elapsed(state) > 60:  # 60 minute max
    return "end"
else:
    return "continue"
```

---

## TUTOR WORKFLOW: COMPLETE FLOW

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  STUDENT    │────►│COORDINATOR  │────►│  EXPLAINER  │────►│   RAG       │
│  (Human)    │     │  AGENT      │     │   MODE      │     │  RETRIEVAL  │
│             │     │             │     │             │     │             │
│ Asks        │     │ Routes to   │     │ Provides    │     │ Gets course │
│ questions   │     │ appropriate │     │ personalized│     │ content     │
│ Gives       │     │ mode based  │     │ explanations│     │ Gets student│
│ feedback    │     │ on state    │     │ Adapts to   │     │ context     │
│ Takes quizzes│     │ Tracks      │     │ sentiment   │     │             │
│             │     │ progress    │     │ learning    │     │             │
└─────────────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
                          │                   │                   │
                          │◄───────────────────┴───────────────────┤
                          │     Returns to Coordinator with     │
                          │     explanation and updated state   │
                          │                                     │
                          ▼                                     │
                   ┌─────────────┐                            │
                   │ GAP_ANALYSIS │◄───────────────────────────┤
                   │   MODE      │                              │
                   │             │                              │
                   │ Identifies  │                              │
                   │ knowledge   │                              │
                   │ gaps       │                              │
                   │ Prioritizes│                              │
                   │ learning   │                              │
                   └──────┬──────┘                              │
                          │                                     │
                          │◄──────────────────────────────────────┤
                          │     Returns gap analysis and plan    │
                          │                                     │
                          ▼                                     │
                   ┌─────────────┐                            │
                   │   QUIZ      │                            │
                   │   MODE      │                            │
                   │             │                            │
                   │ Hard-coded  │                            │
                   │ grading     │                            │
                   │ No LLM      │                            │
                   └──────┬──────┘                            │
                          │                                     │
                          │◄──────────────────────────────────────┤
                          │     Returns quiz results and score    │
                          │                                     │
                          ▼                                     │
                   ┌─────────────┐                            │
                   │  SUMMARIZE  │                            │
                   │    MODE     │                            │
                   │             │                            │
                   │ Shows       │                            │
                   │ progress    │                            │
                   │ Ends        │                            │
                   │ session     │                            │
                   └──────┬──────┘                            │
                          │                                     │
                          ▼                                     │
                   ┌─────────────┐                            │
                   │    END      │                            │
                   └─────────────┘                            │
```

---

## MEMORY AND CHECKPOINTING

### Constructor Checkpointing
- **Location:** `./checkpoints/constructor/session_{session_id}.db`
- **One file per construction session**
- **Stores:** Conversation history, construction state, uploaded files, progress

### Tutor Checkpointing
- **Location:** `./checkpoints/tutor/tutor_sessions.db`
- **Single file for all sessions**
- **Thread-based isolation** (thread_id = session_id)
- **Stores:** Conversation history, mastery snapshot, current topic, quiz state

---

## VECTOR DB COLLECTIONS

### Constructor Vector DB (Per Course)
```
/course_{id}/
├── content_chunks    # All material chunks with embeddings
├── topics            # Topic summaries
├── quiz_questions    # Quiz with embeddings for similarity
└── structure         # Course structure metadata
```

### Student Vector DBs (Per Student, Per Course)
```
/student_{id}/course_{id}/
├── qna_history       # Student's Q&A for personalization
├── explanations      # Cached explanations
├── misconceptions    # Common mistakes for this student
├── learning_style    # Preference data
├── feedback          # Student feelings about course
└── interactions      # All student interactions for context
```

---

# WORKFLOW DOCUMENTATION VERSION

- **Version:** 2.0
- **Last Updated:** 2025-02-10
- **Constructor Workflow Status:** 5/5 Agents Complete (Coordinator ✅, Ingestion ✅, Structure ✅, Quiz ✅, Validation ✅, Orchestration ✅)
- **Tutor Workflow Status:** 1/1 Agent Complete (Session Coordinator ✅ with Explainer/GapAnalysis/Quiz modes)

---

# VISUALIZATION NOTES

For generating visual graphs from this document:

1. **Use Mermaid.js** for flowchart diagrams (compatible with Markdown)
2. **Node Styling:**
   - Rectangle: Process/Action nodes
   - Diamond: Decision/Conditional nodes
   - Rounded Rectangle: Start/End nodes
   - Dotted lines: Feedback loops
3. **Color Coding:**
   - Blue: Coordinator nodes
   - Green: Ingestion nodes
   - Orange: Structure nodes
   - Purple: Quiz nodes
   - Red: Validation nodes
4. **Arrow Labels:** Show data being passed between nodes
