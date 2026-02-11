# Agentic Tutor

> Agent-based learning system that ingests existing course materials and uses coordinated AI agents to plan, retrieve, and adapt study sessions, tracking learner progress and autonomously selecting the most relevant content and activities.

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Node](https://img.shields.io/badge/node-18+-green)
![License](https://img.shields.io/badge/license-MIT-green)

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Docker Deployment](#docker-deployment)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [API Documentation](#api-documentation)
- [Contributing](#contributing)

## Overview

Agentic Tutor is a two-sided AI-powered learning platform with completely separate workflows:

1. **Constructor Workflow** - Course creators interact with AI agents to build courses from raw materials (PDFs, PPTs, videos)
2. **Tutor Workflow** - Students interact with AI agents for adaptive, personalized learning sessions

### Key Differentiators

- **Separate User Systems**: Creators and students have completely isolated authentication and databases
- **Multi-Agent Orchestration**: Each workflow uses coordinated AI agents with specialized roles
- **Adaptive Learning**: The tutor system tracks mastery and personalizes content delivery
- **Real-time Streaming**: Token-by-token response streaming for natural conversation flow

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENTIC TUTOR SYSTEM                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────┐  ┌───────────────────────────────┐ │
│  │      CONSTRUCTOR WORKFLOW           │  │       TUTOR WORKFLOW          │ │
│  │     (Course Creation)               │  │     (Student Learning)        │ │
│  │                                     │  │                               │ │
│  │  Course Creator                     │  │  Student                      │ │
│  │  Coordinator Agent                  │  │  Session Coordinator          │ │
│  │  Ingestion Agent                    │  │  Explainer Agent              │ │
│  │  Structure Analysis Agent           │  │  Assessment Agent             │ │
│  │  Quiz Generation Agent              │  │  Gap Analysis Agent           │ │
│  │  Validation Agent                   │  │  LangGraph Checkpointer       │ │
│  │  LangGraph Checkpointer             │  │  Tutor Tool Layer             │ │
│  │  Constructor Tool Layer             │  │                               │ │
│  │  Course Vector DB                   │  │  Course Vector DB (Read Only) │ │
│  │  Course MySQL DB                    │  │  Course MySQL DB (Read Only)  │ │
│  │                                     │  │  Student Vector DB            │ │
│  │                                     │  │  Student MySQL DB             │ │
│  └─────────────────────────────────────┘  └───────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Features

### For Course Creators (Constructor Workflow)
- **AI-Powered Course Construction**: Upload materials and let AI agents structure your course
- **Multi-Format Support**: PDFs, PowerPoint presentations, videos (with transcription)
- **Automatic Topic Detection**: AI analyzes content and identifies learning topics
- **Prerequisite Mapping**: Automatically identifies relationships between topics
- **Quiz Generation**: AI creates questions from your content
- **Quality Validation**: Built-in validation agent ensures course completeness

### For Students (Tutor Workflow)
- **Adaptive Learning Sessions**: AI tutors adapt to your learning pace and style
- **Knowledge Gap Analysis**: Identifies areas where you need more practice
- **Mastery Tracking**: Per-topic progress tracking with spaced repetition
- **Interactive Quizzes**: Real-time quiz generation during sessions
- **Personalized Explanations**: RAG-based explanations tailored to your level
- **Progress Analytics**: Detailed reports on your learning journey

## Tech Stack

### Backend
| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| AI Agents | LangChain + LangGraph |
| LLM Provider | Z.AI (OpenAI-compatible) |
| Databases | MySQL (separate DBs) |
| Vector Stores | ChromaDB |
| Authentication | JWT |
| File Processing | PyPDF2, python-pptx, faster-whisper |

### Frontend
| Component | Technology |
|-----------|------------|
| Framework | Next.js 14 (App Router) |
| UI Library | shadcn/ui (Radix UI) |
| Styling | Tailwind CSS |
| State | Zustand |
| Forms | React Hook Form + Zod |
| Notifications | Sonner |
| Real-time | WebSocket |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- Z.AI API key (or compatible LLM provider)

### Using Setup Scripts

**Linux/Mac:**
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

**Windows:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\scripts\setup.ps1
```

### Manual Setup

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/agentic-tutor.git
cd agentic-tutor
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your database credentials and API keys
```

3. **Set up databases**
```bash
mysql -u root -p < backend/db/constructor/schema.sql
mysql -u root -p < backend/db/tutor/schema.sql
```

4. **Install backend dependencies**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

5. **Install frontend dependencies**
```bash
cd frontend
npm install
```

## Development Setup

### Start Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend API will be available at `http://localhost:8000`

### Start Frontend

```bash
cd frontend
npm run dev
```

Frontend will be available at `http://localhost:3000`

### Access the Application

- **Creator Login**: http://localhost:3000/auth/login (select Creator tab)
- **Student Login**: http://localhost:3000/auth/login (select Student tab)
- **API Docs**: http://localhost:8000/docs

## Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

Services included:
- `constructor-db` - MySQL database for Constructor workflow (port 3307)
- `tutor-db` - MySQL database for Tutor workflow (port 3308)
- `backend` - FastAPI backend (port 8000)
- `frontend` - Next.js frontend (port 3000)

## Testing

### Run Backend Tests

```bash
cd backend
pytest tests/ -v
```

### Run with Coverage

```bash
pytest tests/ --cov=app --cov-report=html
```

### Run Frontend Tests

```bash
cd frontend
npm test
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Constructor endpoints
curl -X POST http://localhost:8000/api/v1/auth/constructor/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123","full_name":"Test Creator"}'

# Tutor endpoints
curl -X POST http://localhost:8000/api/v1/auth/student/register \
  -H "Content-Type: application/json" \
  -d '{"email":"student@example.com","password":"test123","full_name":"Test Student"}'
```

## Project Structure

```
agentic-tutor/
├── backend/
│   ├── app/
│   │   ├── agents/              # AI agents (Constructor & Tutor)
│   │   │   ├── base/            # Base agent classes
│   │   │   ├── constructor/     # Constructor workflow agents
│   │   │   └── tutor/           # Tutor workflow agents
│   │   ├── api/                 # API endpoints
│   │   ├── core/                # Core utilities
│   │   ├── db/                  # Database models
│   │   ├── vector/              # Vector store wrappers
│   │   └── main.py              # FastAPI application
│   ├── tests/                   # Integration tests
│   ├── data/                    # Data directories
│   └── checkpoints/             # LangGraph checkpoints
├── frontend/
│   ├── app/                     # Next.js pages
│   ├── components/              # React components
│   └── lib/                     # Utilities
├── scripts/                     # Setup scripts
├── docker-compose.yml           # Docker orchestration
└── .env.example                 # Environment template
```

## Environment Variables

Key environment variables (see `.env.example` for complete list):

| Variable | Description | Default |
|----------|-------------|---------|
| `CONSTRUCTOR_DB_URL` | MySQL connection string for Constructor DB | - |
| `TUTOR_DB_URL` | MySQL connection string for Tutor DB | - |
| `LLM_BASE_URL` | LLM API base URL | https://api.z.ai/api/paas/v4/ |
| `LLM_API_KEY` | LLM API key | - |
| `SECRET_KEY` | JWT signing key | - |
| `CORS_ORIGINS` | Allowed CORS origins | http://localhost:3000 |

## API Documentation

Once the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

**Constructor API:**
- `POST /api/v1/constructor/session/start` - Start building a course
- `POST /api/v1/constructor/session/upload` - Upload course materials
- `GET /api/v1/constructor/courses` - List creator's courses

**Tutor API:**
- `GET /api/v1/tutor/courses` - List available courses
- `POST /api/v1/tutor/enroll` - Enroll in a course
- `POST /api/v1/tutor/session/start` - Start a learning session

**WebSocket:**
- `WS /api/v1/constructor/session/ws/{session_id}` - Constructor session streaming
- `WS /api/v1/tutor/session/ws/{session_id}` - Tutor session streaming

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License.

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- AI agents powered by [LangChain](https://langchain.com/) and [LangGraph](https://github.com/langchain-ai/langgraph)
- UI components from [shadcn/ui](https://ui.shadcn.com/)
- LLM provider: [Z.AI](https://api.z.ai/)

---

Made with ❤️ for AI-powered education
