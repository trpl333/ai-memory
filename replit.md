# Peterson Family Insurance AI Phone System

## Overview
This project is an AI-powered phone system for Peterson Family Insurance, featuring the AI agent "Samantha." Built on NeuroSphere Orchestrator and FastAPI, the system provides intelligent call handling with persistent memory, aiming for rapid 2-2.5 second response times. It ensures conversation continuity via an HTTP-based AI-Memory service, integrates external tools for dynamic actions, and employs safety modes for content filtering. The orchestrator acts as middleware between Twilio voice calls and Language Learning Models (LLMs), enhancing conversations through memory retrieval, prompt engineering, and extensible tool functionality. The system has successfully migrated to a microservices architecture and utilizes OpenAI's Realtime API.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
The system operates as a true microservices architecture with complete separation of concerns:

1.  **Phone System (ChatStack)**: A Flask orchestrator (`main.py`) handles Twilio webhooks.
2.  **AI Engine**: A FastAPI backend (`app/main.py`) manages LLM integration and conversation flow.
3.  **AI-Memory Service**: An external HTTP service (http://209.38.143.71:8100) manages all persistent memory and admin configuration.

All admin settings (greetings, voice settings, AI instructions) are stored in the AI-Memory service for dynamic configuration without code deployment.

### UI/UX Decisions
-   **Admin Panel**: A web interface at `/admin.html` provides full control over greeting messages, voice settings, AI personality, and system configuration via the AI-Memory service.
-   **Voice-First Design**: Seamless voice interaction is achieved with ElevenLabs TTS integration.
-   **Real-time Updates**: Admin changes take effect immediately without requiring code deployment.

### Technical Implementations
-   **LLM Integration**: Fully migrated to OpenAI Realtime API (gpt-realtime) for AI responses.
-   **Memory System**: An advanced four-tier Memory V2 system optimized for speed and intelligence, featuring:
    -   **Call Summaries**: AI-generated summaries for faster retrieval.
    -   **Caller Profiles**: Persistent caller information.
    -   **Personality Tracking**: Big 5 traits, communication style, and emotional state.
    -   **Summary-First Retrieval**: AI reads summaries and personality profiles for sub-second retrieval.
    -   A three-tier system for unlimited conversation memory, including rolling thread history, LLM-powered automatic memory consolidation, and permanent durable storage in the AI-Memory Service.
-   **Prompt Engineering**: Uses file-based system prompts for AI personalities, intelligent context packing, and safety triggers.
-   **Tool System**: An extensible, JSON schema-based architecture for external tool execution with a central dispatcher and error recovery.
-   **Data Models**: Pydantic for type-safe validation of request/response models.
-   **Safety & Security**: Multi-tier content filtering, PII protection, rate limiting, and input validation.
-   **Python Frameworks**: Flask and FastAPI.
-   **Database**: PostgreSQL with `pgvector` for vector embeddings and `pgcrypto` for UUIDs.
-   **Containerization**: Docker for deployment using `docker-compose.yml`.
-   **Web Server**: Nginx for HTTPS termination and proxying.
-   **Deployment**: Primarily on DigitalOcean Droplets.

## External Dependencies

### Services
-   **Twilio**: For voice call management and incoming call webhooks.
-   **OpenAI API**: Primary LLM service using GPT Realtime model (`https://api.openai.com/v1/chat/completions`).
-   **ElevenLabs**: For natural voice synthesis and text-to-speech conversion.
-   **AI-Memory Service**: An external HTTP service for conversation memory persistence (`http://209.38.143.71:8100`).

### Databases
-   **PostgreSQL**: Used with `pgvector` extension for conversation memory and semantic search.

### Libraries (Key Examples)
-   **FastAPI** & **Uvicorn**: Web framework and ASGI server.
-   **Pydantic**: Data validation.
-   **NumPy**: Vector operations.
-   **Requests**: HTTP client.
-   **psycopg2**: PostgreSQL adapter.