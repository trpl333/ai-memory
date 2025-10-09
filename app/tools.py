import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tool schemas and definitions
TOOL_SCHEMAS = {
    "book_meeting": {
        "description": "Book a meeting or calendar event",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Meeting title or subject"
                },
                "when": {
                    "type": "string", 
                    "description": "When the meeting should be scheduled (date/time)"
                },
                "with": {
                    "type": "string",
                    "description": "Who should attend the meeting"
                },
                "duration": {
                    "type": "string",
                    "description": "Meeting duration (e.g., '1 hour', '30 minutes')",
                    "default": "1 hour"
                }
            },
            "required": ["title", "when", "with"]
        }
    },
    "send_message": {
        "description": "Send a message via SMS or communication service",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient phone number or contact"
                },
                "message": {
                    "type": "string",
                    "description": "Message content to send"
                },
                "service": {
                    "type": "string",
                    "description": "Communication service to use",
                    "enum": ["sms", "email"],
                    "default": "sms"
                }
            },
            "required": ["to", "message"]
        }
    },
    "search_knowledge": {
        "description": "Search internal knowledge base or documents",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or question"
                },
                "category": {
                    "type": "string",
                    "description": "Knowledge category to search in",
                    "enum": ["general", "technical", "business", "personal"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    "text_to_speech": {
        "description": "Convert text to speech using ElevenLabs or similar service",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to convert to speech"
                },
                "voice": {
                    "type": "string",
                    "description": "Voice to use for synthesis",
                    "default": "default"
                },
                "format": {
                    "type": "string",
                    "description": "Audio format",
                    "enum": ["mp3", "wav"],
                    "default": "mp3"
                }
            },
            "required": ["text"]
        }
    }
}

class ToolDispatcher:
    """
    Tool calling dispatcher with validation and execution.
    """
    
    def __init__(self):
        self.tools = TOOL_SCHEMAS
        
    def validate_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate a tool call against its schema.
        
        Args:
            tool_name: Name of the tool to call
            parameters: Parameters for the tool call
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if tool_name not in self.tools:
            return False, f"Unknown tool: {tool_name}"
        
        schema = self.tools[tool_name]
        required_params = schema["parameters"].get("required", [])
        properties = schema["parameters"].get("properties", {})
        
        # Check required parameters
        for param in required_params:
            if param not in parameters:
                return False, f"Missing required parameter: {param}"
        
        # Basic type validation
        for param, value in parameters.items():
            if param not in properties:
                return False, f"Unknown parameter: {param}"
            
            expected_type = properties[param].get("type")
            if expected_type == "string" and not isinstance(value, str):
                return False, f"Parameter {param} must be a string"
            elif expected_type == "integer" and not isinstance(value, int):
                return False, f"Parameter {param} must be an integer"
        
        return True, ""
    
    def dispatch(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch a tool call to the appropriate handler.
        
        Args:
            tool_name: Name of the tool to call
            parameters: Parameters for the tool call
            
        Returns:
            Tool execution result
        """
        # Validate the tool call
        is_valid, error_msg = self.validate_tool_call(tool_name, parameters)
        if not is_valid:
            return {
                "success": False,
                "result": None,
                "error": error_msg
            }
        
        try:
            # Dispatch to appropriate handler
            if tool_name == "book_meeting":
                return self._book_meeting(parameters)
            elif tool_name == "send_message":
                return self._send_message(parameters)
            elif tool_name == "search_knowledge":
                return self._search_knowledge(parameters)
            elif tool_name == "text_to_speech":
                return self._text_to_speech(parameters)
            else:
                return {
                    "success": False,
                    "result": None,
                    "error": f"Tool {tool_name} not implemented"
                }
                
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            return {
                "success": False,
                "result": None,
                "error": f"Tool execution failed: {str(e)}"
            }
    
    def _book_meeting(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Book a meeting using Cal.com or similar service.
        
        Args:
            params: Meeting parameters
            
        Returns:
            Booking result
        """
        # TODO: Integrate with actual Cal.com API
        # For now, return a simulated successful booking
        
        title = params["title"]
        when = params["when"]
        with_whom = params["with"]
        duration = params.get("duration", "1 hour")
        
        # Simulate booking creation
        booking_id = f"meeting_{hash(f'{title}{when}{with_whom}') % 100000}"
        
        result = f"✅ Meeting '{title}' scheduled for {when} with {with_whom} (Duration: {duration}). Booking ID: {booking_id}"
        
        logger.info(f"Meeting booked: {title} at {when}")
        
        return {
            "success": True,
            "result": result,
            "error": None,
            "booking_id": booking_id
        }
    
    def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a message via SMS or email using Twilio or similar.
        
        Args:
            params: Message parameters
            
        Returns:
            Send result
        """
        # TODO: Integrate with actual Twilio API
        
        to = params["to"]
        message = params["message"]
        service = params.get("service", "sms")
        
        # Simulate message sending
        message_id = f"msg_{hash(f'{to}{message}') % 100000}"
        
        result = f"📱 {service.upper()} sent to {to}: '{message[:50]}...' (Message ID: {message_id})"
        
        logger.info(f"Message sent via {service} to {to}")
        
        return {
            "success": True,
            "result": result,
            "error": None,
            "message_id": message_id
        }
    
    def _search_knowledge(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search internal knowledge base.
        
        Args:
            params: Search parameters
            
        Returns:
            Search results
        """
        # TODO: Integrate with actual knowledge base or document search
        
        query = params["query"]
        category = params.get("category", "general")
        limit = params.get("limit", 5)
        
        # Simulate knowledge search
        mock_results = [
            f"Knowledge item 1 related to '{query}' in {category} category",
            f"Knowledge item 2 about '{query}' with relevant information",
            f"Additional resource on '{query}' topic"
        ]
        
        results = mock_results[:limit]
        result_text = f"🔍 Found {len(results)} knowledge items for '{query}':\n" + "\n".join(f"• {item}" for item in results)
        
        logger.info(f"Knowledge search: '{query}' in {category} - {len(results)} results")
        
        return {
            "success": True,
            "result": result_text,
            "error": None,
            "results": results
        }
    
    def _text_to_speech(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert text to speech using ElevenLabs or similar.
        
        Args:
            params: TTS parameters
            
        Returns:
            TTS result
        """
        # TODO: Integrate with actual ElevenLabs API
        
        text = params["text"]
        voice = params.get("voice", "default")
        format_type = params.get("format", "mp3")
        
        # Simulate TTS generation
        audio_id = f"audio_{hash(text) % 100000}"
        audio_url = f"https://example.com/audio/{audio_id}.{format_type}"
        
        result = f"🔊 Generated speech for text ({len(text)} chars) using {voice} voice. Audio: {audio_url}"
        
        logger.info(f"TTS generated: {len(text)} chars with {voice} voice")
        
        return {
            "success": True,
            "result": result,
            "error": None,
            "audio_url": audio_url,
            "audio_id": audio_id
        }
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools with their schemas.
        
        Returns:
            List of tool definitions
        """
        return [
            {
                "name": name,
                "description": schema["description"],
                "parameters": schema["parameters"]
            }
            for name, schema in self.tools.items()
        ]

# Global tool dispatcher instance
tool_dispatcher = ToolDispatcher()

def parse_tool_calls(assistant_response: str) -> List[Dict[str, Any]]:
    """
    Parse tool calls from assistant response.
    
    This is a simple pattern-based parser. In production, you might want
    to use function calling capabilities of modern LLMs.
    
    Args:
        assistant_response: The assistant's response text
        
    Returns:
        List of parsed tool calls
    """
    tool_calls = []
    
    # Look for tool call patterns like: TOOL:tool_name(param1=value1, param2=value2)
    import re
    
    # Pattern to match tool calls
    pattern = r'TOOL:(\w+)\((.*?)\)'
    matches = re.findall(pattern, assistant_response, re.DOTALL)
    
    for tool_name, params_str in matches:
        try:
            # Parse parameters (simple key=value format)
            params = {}
            if params_str.strip():
                for param_pair in params_str.split(','):
                    if '=' in param_pair:
                        key, value = param_pair.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        params[key] = value
            
            tool_calls.append({
                "name": tool_name,
                "parameters": params
            })
            
        except Exception as e:
            logger.error(f"Failed to parse tool call: {tool_name}({params_str}) - {e}")
    
    return tool_calls

def execute_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Execute a list of tool calls.
    
    Args:
        tool_calls: List of tool calls to execute
        
    Returns:
        List of execution results
    """
    results = []
    
    for tool_call in tool_calls:
        try:
            result = tool_dispatcher.dispatch(
                tool_call["name"],
                tool_call["parameters"]
            )
            results.append(result)
            
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            results.append({
                "success": False,
                "result": None,
                "error": f"Execution failed: {str(e)}"
            })
    
    return results
