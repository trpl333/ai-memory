import os
import requests
import logging
import json
import threading
import time
from queue import Queue
from typing import List, Dict, Any, Tuple, Generator, Optional
from config_loader import get_llm_config
try:
    from websocket import WebSocketApp
except ImportError:
    WebSocketApp = None
    logging.warning("WebSocketApp not available - realtime streaming disabled")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _get_llm_config():
    """Get LLM configuration dynamically for hot reload support"""
    return get_llm_config()

def _get_headers():
    """Get request headers dynamically for hot reload support"""
    config = _get_llm_config()
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = f"Bearer {config['api_key']}"
    return headers

def chat(messages: List[Dict[str, str]], temperature: float = 0.6, top_p: float = 0.9, max_tokens: int = 800) -> Tuple[str, Dict[str, Any]]:
    """
    Call the LLM endpoint with the provided messages and parameters.
    
    Args:
        messages: List of message dicts with 'role' and 'content' keys
        temperature: Sampling temperature (0.0 to 2.0)
        top_p: Top-p sampling parameter (0.0 to 1.0)
        max_tokens: Maximum tokens to generate
        
    Returns:
        Tuple of (response_content, usage_stats)
    """
    # Get current configuration
    config = _get_llm_config()
    base_url = config["base_url"]
    model = config["model"]
    headers = _get_headers()
    
    # Check if using mock endpoint for development
    if base_url == "http://localhost:8000":
        return _mock_llm_response(messages, temperature, top_p, max_tokens)
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens
    }
    
    try:
        logger.info(f"Calling LLM with {len(messages)} messages, temp={temperature}, top_p={top_p}")
        
        # Handle base_url that may or may not include /v1
        endpoint_url = f"{base_url}/chat/completions" if base_url.endswith('/v1') else f"{base_url}/v1/chat/completions"
        
        response = requests.post(
            endpoint_url,
            json=payload,
            headers=headers,
            timeout=120  # Increased timeout for longer responses
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Extract response content and usage stats
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        
        logger.info(f"LLM response received: {usage.get('total_tokens', 0)} total tokens")
        
        return content, usage
        
    except requests.exceptions.Timeout:
        logger.error("LLM request timeout")
        raise Exception("LLM request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        logger.error(f"Failed to connect to LLM at {base_url}")
        raise Exception("Failed to connect to LLM service. Please check configuration.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"LLM HTTP error: {e}")
        raise Exception(f"LLM service error: {e}")
    except KeyError as e:
        logger.error(f"Unexpected LLM response format: {e}")
        raise Exception("Unexpected response format from LLM service.")
    except Exception as e:
        logger.error(f"Unexpected error calling LLM: {e}")
        raise Exception(f"LLM service error: {str(e)}")

def _mock_llm_response(messages: List[Dict[str, str]], temperature: float, top_p: float, max_tokens: int) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a mock LLM response for development/testing.
    """
    logger.info(f"Using mock LLM response for {len(messages)} messages")
    
    # Get the last user message
    user_message = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_message = msg["content"]
            break
    
    # Generate a simple contextual response
    if "hello" in user_message.lower() or "hi" in user_message.lower():
        response = "Hello! I'm Sam, your AI assistant. I'm running in development mode right now. How can I help you today?"
    elif "weather" in user_message.lower():
        response = "I'd love to help with weather information, but I'm currently running in mock mode. In a real deployment, I would call a weather API to get current conditions."
    elif "tool" in user_message.lower() or "book" in user_message.lower():
        response = "I can help with tool calls! Try asking me to book a meeting or send a message. I'll demonstrate the tool calling functionality."
    elif "remember" in user_message.lower():
        response = "I'll remember that information! My memory system is working and will store important details from our conversation for future reference."
    else:
        response = f"I understand you're asking about: '{user_message[:100]}...' I'm currently running in development mode with a mock LLM. In production, I would provide a more detailed and helpful response using a real language model."
    
    # Mock usage statistics
    usage = {
        "prompt_tokens": sum(len(msg["content"].split()) for msg in messages),
        "completion_tokens": len(response.split()),
        "total_tokens": sum(len(msg["content"].split()) for msg in messages) + len(response.split())
    }
    
    return response, usage

def chat_realtime_stream(messages: List[Dict[str, str]], temperature: float = 0.6, max_tokens: int = 800) -> Generator[str, None, None]:
    """
    Stream response from OpenAI Realtime API using WebSocket connection.
    
    Args:
        messages: List of message dicts with 'role' and 'content' keys
        temperature: Sampling temperature (0.0 to 2.0)
        max_tokens: Maximum tokens to generate
        
    Yields:
        Individual tokens/words from the streaming response
    """
    if WebSocketApp is None:
        logger.warning("WebSocket not available - falling back to regular chat")
        # Fallback to regular chat completions
        response_content, _ = chat(messages, temperature=temperature, max_tokens=max_tokens)
        words = response_content.split()
        for word in words:
            yield word + " "
        return
    
    config = _get_llm_config()
    base_url = config["base_url"]
    model = config["model"]
    api_key = config["api_key"]
    
    if not api_key:
        logger.error("No API key available for realtime connection")
        yield "I'm sorry, I'm having trouble connecting right now."
        return
    
    # Convert base_url to WebSocket URL
    ws_url = base_url.replace("https://", "wss://").replace("/v1", "/v1/realtime")
    ws_url += f"?model={model}"
    
    # Thread-safe queue for streaming tokens
    token_queue = Queue()
    response_complete = False
    error_occurred = False
    response_text = ""
    
    def on_message(ws, message):
        nonlocal response_complete, error_occurred, response_text
        try:
            data = json.loads(message)
            event_type = data.get("type")
            
            if event_type == "response.text.delta":
                delta = data.get("delta", "")
                response_text += delta
                # Put tokens in queue for streaming
                if delta:
                    token_queue.put(delta)
                    
            elif event_type == "response.text.done":
                response_complete = True
                token_queue.put(None)  # Signal end of stream
                
            elif event_type == "error":
                error_msg = data.get("error", {}).get("message", "Unknown error")
                logger.error(f"Realtime API error: {error_msg}")
                error_occurred = True
                response_complete = True
                token_queue.put(None)  # Signal end of stream
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from realtime API: {message}")
        except Exception as e:
            logger.error(f"Error processing realtime message: {e}")
    
    def on_error(ws, error):
        nonlocal error_occurred, response_complete
        logger.error(f"WebSocket error: {error}")
        error_occurred = True
        response_complete = True
        token_queue.put(None)  # Signal end of stream
    
    def on_close(ws, close_status_code, close_msg):
        nonlocal response_complete
        response_complete = True
        token_queue.put(None)  # Signal end of stream
    
    def on_open(ws):
        try:
            # Send session configuration with dynamic instructions
            system_context = " ".join([m["content"] for m in messages if m["role"] == "system"])
            if not system_context:
                system_context = "You are Samantha, a helpful AI assistant for Peterson Family Insurance Agency."
            
            session_config = {
                "type": "session.update", 
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": system_context,
                    "temperature": temperature
                }
            }
            ws.send(json.dumps(session_config))
            
            # Send full conversation history
            for i, message in enumerate(messages):
                if message["role"] == "user":
                    conversation_input = {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": message["content"]
                                }
                            ]
                        }
                    }
                    ws.send(json.dumps(conversation_input))
                else:  # assistant messages
                    conversation_input = {
                        "type": "conversation.item.create", 
                        "item": {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": message["content"]
                                }
                            ]
                        }
                    }
                    ws.send(json.dumps(conversation_input))
            
            # Request response with instructions - THIS IS THE CRITICAL FIX!
            # Build conversation context for instructions
            conversation_text = " ".join([m["content"] for m in messages if m["role"] == "user"])
            system_context = " ".join([m["content"] for m in messages if m["role"] == "system"])
            full_instructions = f"{system_context} {conversation_text}".strip()
            
            response_create = {
                "type": "response.create",
                "response": {
                    "max_output_tokens": max_tokens,
                    "temperature": temperature
                }
            }
            ws.send(json.dumps(response_create))
            
        except Exception as e:
            logger.error(f"Error sending to realtime API: {e}")
            error_occurred = True
            token_queue.put(None)
    
    try:
        # Create WebSocket connection
        ws = WebSocketApp(
            ws_url,
            header=[f"Authorization: Bearer {api_key}", "OpenAI-Beta: realtime=v1"],
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        # Run WebSocket in a separate thread
        def run_websocket():
            ws.run_forever()
        
        ws_thread = threading.Thread(target=run_websocket, daemon=True)
        ws_thread.start()
        
        # Stream tokens from the queue
        timeout = 120  # Increased for production robustness
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            try:
                # Get token from queue with timeout
                token = token_queue.get(timeout=0.5)
                
                if token is None:  # End of stream signal
                    break
                    
                # Yield token - split into words for better streaming
                words = token.split()
                for word in words:
                    if word:
                        yield word + " "
                        
            except:
                # Queue timeout - check if we should continue waiting
                if response_complete:
                    break
                continue
        
        # Handle error cases
        if error_occurred:
            if not response_text.strip():  # No content received
                yield "I'm sorry, I encountered an error. Please try again."
        elif not response_text.strip() and not error_occurred:
            yield "I'm sorry, I didn't receive a complete response. Please try again."
        
        # Close WebSocket
        try:
            ws.close()
        except:
            pass
        
    except Exception as e:
        logger.error(f"Realtime API connection error: {e}")
        yield "I'm sorry, I'm having trouble connecting to the service right now."

def validate_llm_connection() -> bool:
    """
    Validate that the LLM service is accessible.
    
    Returns:
        True if connection is valid, False otherwise
    """
    try:
        test_messages = [{"role": "user", "content": "Hello"}]
        
        # Try regular chat completions for validation (more reliable)
        chat(test_messages, max_tokens=10)
        logger.info("LLM connection validation successful")
        return True
        
    except Exception as e:
        logger.error(f"LLM connection validation failed: {e}")
        return False
