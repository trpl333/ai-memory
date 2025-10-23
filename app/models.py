from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

class Message(BaseModel):
    role: MessageRole
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: int = Field(default=200, ge=1, le=4000)
    safety_mode: bool = Field(default=False)

class ChatResponse(BaseModel):
    output: str
    used_memories: List[str] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    memory_count: int = 0

class MemoryObject(BaseModel):
    id: Optional[str] = None
    type: str  # person, preference, project, rule, moment, fact
    key: str
    value: Dict[str, Any]
    ttl_days: int = 365
    source: str = "orchestrator"

class ToolCall(BaseModel):
    name: str
    parameters: Dict[str, Any]

class ToolResponse(BaseModel):
    result: str
    success: bool
    error: Optional[str] = None

# Memory V2 Models
class ProcessCallRequest(BaseModel):
    user_id: str
    thread_id: str
    conversation_history: List[List[str]]  # List of [role, content] pairs

class EnrichedContextRequest(BaseModel):
    user_id: str
    num_summaries: Optional[int] = 5

class SearchSummariesRequest(BaseModel):
    user_id: str
    query: str
    limit: Optional[int] = 5
