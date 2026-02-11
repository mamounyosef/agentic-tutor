# Agentic Tutor Workflows

This document describes the implemented workflow logic in the current codebase.

## Scope
- Backend workflow graphs and node routing for Constructor and Tutor agents.
- API turn processing for REST and WebSocket endpoints.
- Tracing hooks (LangSmith/LangChain runnable config).

## Runtime Architecture
- Session graph instances are kept in memory:
  - Constructor: `_constructor_sessions` in `backend/app/api/constructor.py`
  - Tutor: `_tutor_sessions` in `backend/app/api/tutor.py`
- LangGraph checkpointer used by both coordinators: `MemorySaver` (in-process memory).
- Message lists may include dict messages and LangChain message objects; runtime normalizes via `backend/app/agents/base/message_utils.py`.

---

## Constructor Workflow

### Coordinator Graph
File: `backend/app/agents/constructor/coordinator/agent.py`

Nodes:
- `welcome`
- `intake`
- `route_action`
- `dispatch`
- `respond`
- `finalize`
- `end_turn`
- sub-agent wrappers: `ingestion`, `structure`, `quiz`, `validation`

Entry point:
- `welcome`

Main edges:
- `welcome -> intake`
- `intake -> route_action`
- `route_action -> {end_turn | dispatch | finalize}` via `route_by_phase`
- `dispatch -> {respond | ingestion | structure | quiz | validation}` via `route_subagent`
- `ingestion|structure|quiz|validation -> respond`
- `respond -> {end_turn | END}` via `should_continue`
- `finalize -> END`
- `end_turn -> END`

Important behavior:
- `welcome_node` is idempotent for existing sessions (does not reset state after session initialization).
- Coordinator phase key is canonical `phase` in state.
- `collect_info`, `request_files`, and conversational `respond` actions terminate the current turn (`end_turn`) instead of self-looping without new user input.
- `route_action` validates LLM-proposed actions against the allowed action set; invalid values fall back to deterministic state-based action selection.
- `intake`/`respond` apply a deterministic fallback message if the model returns empty content.

### Sub-Agent Pipelines

#### Ingestion
File: `backend/app/agents/constructor/ingestion/agent.py`

Pipeline:
- `detect_types -> extract -> chunk -> store -> report -> END`

#### Structure
File: `backend/app/agents/constructor/structure/agent.py`

Pipeline:
- `analyze_content -> detect_topics -> group_into_units -> identify_prerequisites -> build_hierarchy -> validate_structure -> suggest_organization -> finalize_structure -> END`

#### Quiz Generation
File: `backend/app/agents/constructor/quiz_gen/agent.py`

Pipeline:
- `plan_quiz_generation -> select_topic`
- `select_topic -> generate_questions` or `finalize_quiz_bank`
- `generate_questions -> validate_questions -> create_rubrics -> check_completion`
- `check_completion -> select_topic` or `finalize_quiz_bank`
- `finalize_quiz_bank -> END`

#### Validation
File: `backend/app/agents/constructor/validation/agent.py`

Pipeline:
- `validate_content -> validate_structure -> validate_quiz -> calculate_readiness -> generate_report -> END`

### Constructor API Integration
File: `backend/app/api/constructor.py`

REST endpoints:
- `POST /api/v1/constructor/session/start`
- `POST /api/v1/constructor/session/chat`
- `GET /api/v1/constructor/session/status/{session_id}`
- file upload and course endpoints

WebSocket endpoint:
- `/api/v1/constructor/session/ws/{session_id}`

Turn processing rules:
- User input is appended as canonical dict message via `append_user_message`.
- Outbound assistant text uses `latest_assistant_content` to safely support mixed message types.
- API response keeps `construction_phase` for compatibility, mapped from state key `phase`.
- LLM fallback errors use in-scope `settings` in websocket and REST handlers.
- Session turns are bounded to a single pass (`... -> end_turn -> END`) to avoid recursive intra-turn loops.
- `POST /constructor/session/upload` now synchronizes graph session state (`uploaded_files`, `processed_files`, `content_chunks`) so subsequent routing decisions reflect actual uploaded/processed materials.
- Upload ingestion calls constructor ingestion tools through official tool invocation (`.ainvoke`) with the correct parameter schema.

Orchestrator correction:
- Prerequisite title mapping now resolves by topic ID (not list index).
  - File: `backend/app/agents/constructor/orchestration.py`

---

## Tutor Workflow

### Coordinator Graph
File: `backend/app/agents/tutor/graph.py`

Nodes:
- `welcome`
- `intake`
- `explainer`
- `gap_analysis`
- `quiz`
- `grade_quiz`
- `summarize`
- `end_turn`

Entry point:
- `welcome`

Main edges:
- `welcome -> intake`
- `intake -> {explainer | gap_analysis | quiz | grade_quiz | summarize | end_turn}` via `route_by_action`
- `explainer -> {quiz | intake}` via `route_after_explainer`
- `gap_analysis -> intake`
- `quiz -> {quiz | intake}` via `route_after_quiz`
- `grade_quiz -> {quiz | intake}` via `route_after_quiz`
- `summarize -> END`
- `end_turn -> END`

Important logic fixes:
- Removed conflicting second conditional routing from `intake`.
- Removed invalid route target (`respond`) from tutor routing map.
- `welcome_node` is idempotent for existing sessions (prevents repeated re-initialization).
- `ask_goal` now routes to `end_turn` (prevents self-loop recursion when no fresh user input exists).
- Tutor support modules are plain async callables (not LangChain tool wrappers) so coordinator nodes can invoke them directly without `StructuredTool` call errors.

### Quiz Turn Lifecycle

State fields:
- `current_quiz`
- `quiz_position`
- `quiz_completed`
- `awaiting_quiz_answer`
- `last_answer_correct`
- `last_feedback`

Flow:
1. User requests quiz (`next_action = quiz`).
2. `quiz_node` initializes quiz (if needed), sends current question, sets `awaiting_quiz_answer = True`.
3. Graph returns to `intake` and ends turn (`end_turn`) until new user input arrives.
4. Next user input while awaiting answer maps to `next_action = quiz_answer`.
5. `grade_quiz_node` grades answer, stores `last_answer_correct` and `last_feedback`, advances `quiz_position`, sets `awaiting_quiz_answer = False`.
6. If questions remain, graph revisits `quiz_node` to send the next question; otherwise finalizes quiz and returns to intake mode.

### Tutor API Integration
File: `backend/app/api/tutor.py`

REST endpoints:
- `POST /api/v1/tutor/session/start`
- `POST /api/v1/tutor/session/chat`
- session status/end + course/progress endpoints

WebSocket endpoint:
- `/api/v1/tutor/session/ws/{session_id}`

Turn processing rules:
- User messages appended via `append_user_message`.
- Assistant extraction uses `latest_assistant_content`.
- `quiz_answer` websocket event appends answer into message history and invokes graph; feedback is read from `last_feedback`.
- Fallback LLM connection message now uses in-scope websocket settings.

---

## Message Model and Normalization

File: `backend/app/agents/base/message_utils.py`

Provided utilities:
- `message_content(...)`
- `message_role(...)`
- `is_assistant_message(...)`
- `make_user_message(...)`
- `make_assistant_message(...)`
- `latest_assistant_content(...)`
- `append_user_message(...)`

Why it exists:
- APIs and nodes receive mixed message shapes (`dict` and LangChain message objects).
- Normalization removes `.get` attribute errors on message objects.

---

## Vector Store Runtime Compatibility

Files:
- `backend/app/vector/constructor_store.py`
- `backend/app/vector/student_store.py`

Runtime notes:
- Chroma settings imports are disambiguated from app settings to avoid `persist_directory` field errors.
- LangChain Chroma wrappers use the embeddings client object (`OpenAIEmbeddings`) rather than a single-text callable.
- Multi-field metadata filters are normalized to Chroma-compatible `$and` filters.
- Raw Chroma `get/query/peek` payloads are normalized before use, so higher-level tutor/constructor tools consume consistent `id/content/metadata` rows.

---

## LangSmith Tracing Integration

### Configuration
- `backend/app/core/config.py` adds:
  - `LANGSMITH_TRACING`
  - `LANGSMITH_API_KEY`
  - `LANGSMITH_ENDPOINT`
  - `LANGSMITH_PROJECT`
  - `LANGSMITH_WORKSPACE_ID`

- Environment templates updated:
  - `.env.example`
  - `.env`
  - `backend/.env`

### Startup Initialization
- File: `backend/app/main.py`
- Calls `initialize_langsmith(settings)` during app startup.
- Helper file: `backend/app/observability/langsmith.py`

### Tagged Invocation Config
- APIs build runnable config via `build_trace_config(...)` and attach:
  - tags (for example: `constructor`, `tutor`, `websocket`, `rest`, `quiz`)
  - metadata (`session_id`, `user_id`, `course_id`, endpoint)

This drives LangSmith/LangChain trace grouping without changing endpoint contracts.

---

## Frontend/Backend Contract Notes

- Constructor auth redirect target remains `/constructor/dashboard`.
- Constructor session response still returns `construction_phase` key for compatibility, sourced from backend state `phase`.
- Tutor and Constructor WebSocket token streams now safely handle both dict and LangChain assistant messages.

---

## Validation Checklist

Use this checklist after backend changes:

1. Auth endpoints still return valid token payloads.
2. Constructor:
   - start session returns `201` and `session_id`
   - websocket `message` produces assistant tokens
   - status endpoint reports `phase`-backed state
3. Tutor:
   - start session returns welcome message
   - normal chat returns assistant response
   - quiz request shows question, answer triggers grade, and next question waits for new input
4. No runtime errors for mixed message access (`.get` on `AIMessage`/`HumanMessage`).
5. LangSmith traces appear when tracing is enabled and API key is configured.

---

## Document Version
- Version: 3.0
- Last updated: 2026-02-11
- Source of truth: implementation in `backend/app/agents/*` and `backend/app/api/*`
