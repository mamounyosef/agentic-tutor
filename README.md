# Agentic Tutor

> A dual-workflow learning platform powered by LangGraph multi-agent orchestration: creators build courses from raw materials, and students learn through adaptive, personalized tutoring sessions.

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Node](https://img.shields.io/badge/node-18+-green)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

## Table of Contents

- [Overview](#overview)
- [Core Workflows](#core-workflows)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Repository Layout](#repository-layout)
- [Local Setup](#local-setup)
- [Environment Variables](#environment-variables)
- [API Summary](#api-summary)
- [LangSmith Tracing](#langsmith-tracing)
- [Workflow Visualization](#workflow-visualization)
- [Docker](#docker)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Overview

Agentic Tutor is built around two separate but connected experiences:

1. **Constructor Workflow (Creator Side)**
   - Ingests creator materials (PDF, PPT/PPTX, DOCX, TXT, video).
   - Builds course structure (units/topics), generates quizzes, validates readiness.
   - Supports streaming coordination via WebSocket.

2. **Tutor Workflow (Student Side)**
   - Provides interactive tutoring sessions with dynamic routing (explain, quiz, summarize, etc.).
   - Tracks mastery and supports progress-aware study loops.
   - Uses streaming responses via WebSocket with HTTP fallback.

Both workflows are modeled as **LangGraph graphs** with checkpointed session state and explicit node-level orchestration.

## Core Workflows

### Constructor (Creator)

Top-level coordinator routes across sub-agents:

- **Coordinator nodes:** `welcome`, `intake`, `route_action`, `dispatch`, `respond`, `finalize`, `end_turn`
- **Sub-agents:**
  - Ingestion graph
  - Structure graph
  - Quiz generation graph
  - Validation graph

Detailed workflow documentation lives in `WORKFLOWS.md`.

### Tutor (Student)

Tutor coordinator nodes include:

- `welcome`, `intake`, `explainer`, `gap_analysis`, `quiz`, `grade_quiz`, `summarize`, `end_turn`

Routing is conditional and state-aware, enabling adaptive instructional turns.

## Architecture

```text
Frontend (Next.js)
  -> REST + WebSocket
Backend (FastAPI)
  -> Auth API
  -> Constructor API + WebSocket
  -> Tutor API + WebSocket
  -> LangGraph Workflows (Constructor + Tutor)
  -> SQLAlchemy (Constructor DB, Tutor DB)
  -> Chroma Vector Stores
  -> Optional LangSmith tracing
```

Data boundaries are separated between creator and student domains while enabling published course consumption by tutor flows.

## Tech Stack

### Backend

- Python 3.11+
- FastAPI
- LangChain + LangGraph
- SQLAlchemy + MySQL
- ChromaDB
- JWT auth
- File ingestion stack: PDF/PPT/DOCX/text/video tooling

### Frontend

- Next.js 14 (App Router)
- React 18
- TypeScript
- Tailwind CSS
- Zustand
- WebSocket client streaming

## Repository Layout

```text
agentic-tutor/
|-- backend/
|   |-- app/
|   |   |-- agents/
|   |   |   |-- constructor/
|   |   |   `-- tutor/
|   |   |-- api/
|   |   |-- core/
|   |   |-- db/
|   |   |-- observability/
|   |   `-- vector/
|   |-- db/
|   |   |-- constructor/schema.sql
|   |   `-- tutor/schema.sql
|   `-- requirements.txt
|-- frontend/
|-- scripts/
|   |-- setup.ps1
|   |-- setup.sh
|   |-- visualize_langgraphs.py
|   `-- visualize_langgraphs_combined.py
|-- artifacts/langgraph_viz/
|-- WORKFLOWS.md
|-- docker-compose.yml
`-- .env.example
```

## Local Setup

### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- MySQL 8+
- An OpenAI-compatible LLM endpoint (local or remote)

### 2. Clone

```bash
git clone https://github.com/mamounyosef/agentic-tutor.git
cd agentic-tutor
```

### 3. Configure Environment

Create env files:

```bash
cp .env.example .env
cp .env.example backend/.env
```

Important note:

- Backend settings load from `.env` in the backend working directory when you run backend commands from `backend/`.
- In practice, keep `backend/.env` updated for backend runtime.

### 4. Initialize Databases

```bash
mysql -u root -p < backend/db/constructor/schema.sql
mysql -u root -p < backend/db/tutor/schema.sql
```

### 5. Run Backend

From terminal 1:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Run Frontend

From terminal 2:

```powershell
cd frontend
npm install
npm run dev
```

### 7. Access

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Environment Variables

See `.env.example` for full config. Key values:

### Core

- `APP_NAME`, `APP_ENV`, `DEBUG`
- `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`
- `CORS_ORIGINS`

### Databases

- `CONSTRUCTOR_DB_URL`
- `TUTOR_DB_URL`

### LLM + Embeddings

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_TEMPERATURE`
- `LLM_MAX_TOKENS`
- `EMBEDDINGS_BASE_URL`
- `EMBEDDINGS_API_KEY`
- `EMBEDDINGS_MODEL`

### Transcription

- `TRANSCRIPTION_SERVICE`
- `TRANSCRIPTION_MODEL_SIZE`
- `TRANSCRIPTION_DEVICE`
- `TRANSCRIPTION_COMPUTE_TYPE`

### LangSmith

- `LANGSMITH_TRACING`
- `LANGSMITH_API_KEY`
- `LANGSMITH_ENDPOINT`
- `LANGSMITH_PROJECT`
- `LANGSMITH_WORKSPACE_ID`

## API Summary

All endpoints are under `/api/v1`.

### Auth

- `POST /auth/creator/register`
- `POST /auth/creator/login`
- `GET /auth/creator/me`
- `POST /auth/student/register`
- `POST /auth/student/login`
- `GET /auth/student/me`

### Constructor

- `POST /constructor/session/start`
- `POST /constructor/session/chat`
- `POST /constructor/session/upload`
- `GET /constructor/session/status/{session_id}`
- `POST /constructor/course/finalize`
- `GET /constructor/courses`
- `GET /constructor/course/{course_id}`
- `WS /constructor/session/ws/{session_id}`

### Tutor

- `GET /tutor/courses`
- `GET /tutor/course/{course_id}`
- `POST /tutor/enroll`
- `POST /tutor/session/start`
- `POST /tutor/session/chat`
- `GET /tutor/session/{session_id}`
- `POST /tutor/session/end`
- `GET /tutor/student/{student_id}/progress/{course_id}`
- `GET /tutor/student/{student_id}/mastery`
- `GET /tutor/student/{student_id}/gaps`
- `POST /tutor/quiz/answer`
- `GET /tutor/course/{course_id}/quiz/question`
- `WS /tutor/session/ws/{session_id}`

## LangSmith Tracing

Tracing is integrated and fail-open.

To enable:

1. Set in `backend/.env`:
   - `LANGSMITH_TRACING=true`
   - `LANGSMITH_API_KEY=...`
   - `LANGSMITH_PROJECT=agentic-tutor`
2. Restart backend.

If traces are missing, verify backend is using `backend/.env` and the API key is valid.

## Workflow Visualization

Two scripts are provided:

### 1. Per-workflow exports

```powershell
backend\venv\Scripts\python scripts\visualize_langgraphs.py --png
```

Outputs to `artifacts/langgraph_viz/`:

- Mermaid (`.mmd`)
- JSON (`.json`)
- PNG (`.png`)
- Export index (`README.md`, `summary.json`)

### 2. Combined workflow mega-diagram

```powershell
backend\venv\Scripts\python scripts\visualize_langgraphs_combined.py --png
```

Outputs:

- `artifacts/langgraph_viz/combined/all_workflows.mmd`
- `artifacts/langgraph_viz/combined/all_workflows.json`
- `artifacts/langgraph_viz/combined/all_workflows.png`

## Docker

Docker files and `docker-compose.yml` are included for containerized runs.

Quick start:

```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

For local debugging and workflow iteration, running backend/frontend directly in two terminals is still recommended.

## Troubleshooting

### WebSocket fallback appears in UI

- Confirm backend is reachable at `http://localhost:8000`.
- Confirm frontend env (`NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_WS_URL`) points to the backend.

### No LangSmith traces

- Confirm `LANGSMITH_TRACING=true` and valid `LANGSMITH_API_KEY` in `backend/.env`.
- Restart backend after env changes.

### LLM connection errors

- Check `LLM_BASE_URL` and model availability.
- For local servers, verify model is loaded before chat/session starts.

### Large video ingestion issues

- Try shorter clips or lower transcription model size.
- Ensure ffmpeg and transcription dependencies are installed.

## License

Licensed under the **Apache License 2.0**. See `LICENSE`.
