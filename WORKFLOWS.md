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

*Note: This workflow will be implemented in Phase 5-6. Documentation will be added when implemented.*

---

# WORKFLOW DOCUMENTATION VERSION

- **Version:** 1.1
- **Last Updated:** 2025-02-10
- **Constructor Workflow Status:** 5/5 Agents Complete (Coordinator ✅, Ingestion ✅, Structure ✅, Quiz ✅, Validation ✅, Orchestration ✅)
- **Tutor Workflow Status:** Not Started

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
