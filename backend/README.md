# Agentic Tutor Backend

FastAPI backend for the Agent-based learning system.

## Running the Server

```bash
# Development
uvicorn backend.app.main:app --reload

# Production
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
