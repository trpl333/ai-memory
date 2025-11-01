# AI-Memory Service (NeuroSphere Ecosystem)

## Overview
AI-Memory is a shared microservice within the NeuroSphere ecosystem, providing persistent memory storage, AI-driven call summarization, and personality tracking. It significantly improves retrieval speed (under 1 second) by utilizing AI-generated summaries instead of raw conversation data. The service offers REST API endpoints for efficient memory management, context enrichment, and dynamic configuration of AI behaviors. Its purpose is to act as the central brain for AI agents, enabling them to remember past interactions, understand user personalities, and provide highly personalized and contextually relevant responses.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
The system employs a microservices architecture, separating concerns into a Phone System (ChatStack), an AI Engine, and the AI-Memory Service. All dynamic configurations, including greetings, voice settings, and AI instructions, are stored in the AI-Memory service, allowing for real-time updates without code deployments.

### UI/UX Decisions
-   **Admin Panel**: A web-based interface (`/admin.html`) provides comprehensive control over AI settings, greetings, and voice configurations.
-   **Voice-First Design**: Emphasizes seamless voice interaction, supported by ElevenLabs TTS.
-   **Real-time Updates**: Configuration changes via the admin panel are applied instantly.

### Technical Implementations
-   **LLM Integration**: Utilizes OpenAI's Realtime API for dynamic AI responses.
-   **Memory System**: Features a four-tier Memory V2 system for speed and intelligence:
    -   AI-generated call summaries for rapid context retrieval.
    -   Persistent caller profiles and personality tracking (Big 5 traits, communication style, emotional state).
    -   Summary-first retrieval mechanism for sub-second context loading.
    -   Three-tier system for unlimited conversation memory: rolling thread history, LLM-powered consolidation, and permanent durable storage.
-   **Prompt Engineering**: Employs file-based system prompts, intelligent context packing, and safety triggers.
-   **Tool System**: Extensible, JSON schema-based architecture for external tool execution with error recovery.
-   **Data Models**: Pydantic for robust data validation.
-   **Safety & Security**: Includes content filtering, PII protection, rate limiting, and input validation.
-   **Backend Frameworks**: FastAPI.
-   **Database**: PostgreSQL with `pgvector` for vector embeddings and `pgcrypto` for UUIDs.
-   **Containerization**: Docker for deployment.
-   **Web Server**: Nginx for HTTPS termination and proxying.

## External Dependencies

### Services
-   **Twilio**: For voice call management and webhooks.
-   **OpenAI API**: Primary LLM service (GPT Realtime model).
-   **ElevenLabs**: For text-to-speech synthesis.
-   **AI-Memory Service**: External HTTP service for memory persistence.

### Databases
-   **PostgreSQL**: Used with `pgvector` for conversation memory and semantic search.