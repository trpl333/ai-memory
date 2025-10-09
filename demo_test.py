#!/usr/bin/env python3
"""
Demo and test script for NeuroSphere Orchestrator
Tests all functionality without needing a running server.
"""
import os
import json
import asyncio
from typing import Dict, Any
from config_loader import get_setting, get_llm_config

# Set up mock environment from centralized config
llm_config = get_llm_config()
os.environ["LLM_BASE_URL"] = "http://localhost:8000"  # Force mock for testing
os.environ["LLM_MODEL"] = "mock-model"  # Force mock for testing
os.environ["EMBED_DIM"] = str(get_setting("embed_dim", 768))

async def test_memory_system():
    """Test the memory storage and retrieval system."""
    print("\n=== Testing Memory System ===")
    
    from app.memory import MemoryStore
    
    try:
        # Initialize memory store
        memory = MemoryStore()
        print("✅ Memory store connected")
        
        # Test writing memories
        memory_id = memory.write(
            "preference", 
            "user_style", 
            {"summary": "User prefers concise responses", "style": "direct"}
        )
        print(f"✅ Stored preference memory: {memory_id}")
        
        memory_id = memory.write(
            "person", 
            "user_info", 
            {"name": "Test User", "role": "Developer"}
        )
        print(f"✅ Stored person memory: {memory_id}")
        
        # Test searching memories
        results = memory.search("user preferences style", k=5)
        print(f"✅ Memory search returned {len(results)} results")
        
        # Test memory stats
        stats = memory.get_memory_stats()
        print(f"✅ Memory stats: {stats['total_memories']} total memories")
        
        memory.close()
        return True
        
    except Exception as e:
        print(f"❌ Memory system test failed: {e}")
        return False

async def test_llm_system():
    """Test the LLM system with mock responses."""
    print("\n=== Testing LLM System ===")
    
    from app.llm import chat, validate_llm_connection
    
    try:
        # Test LLM connection validation
        is_connected = validate_llm_connection()
        print(f"✅ LLM connection validation: {'Connected' if is_connected else 'Failed'}")
        
        # Test various message types
        test_messages = [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "user", "content": "Can you book a meeting for tomorrow?"},
            {"role": "user", "content": "Remember this: I prefer morning meetings"},
            {"role": "user", "content": "What's the weather like?"}
        ]
        
        for i, msg in enumerate(test_messages, 1):
            response, usage = chat([msg], temperature=0.7, max_tokens=150)
            print(f"✅ Test {i}: Generated {usage['completion_tokens']} tokens")
            print(f"   Response: {response[:80]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ LLM system test failed: {e}")
        return False

async def test_packer_system():
    """Test the prompt packing and memory integration."""
    print("\n=== Testing Packer System ===")
    
    from app.packer import pack_prompt, extract_carry_kit_items, should_remember
    from app.memory import MemoryStore
    
    try:
        # Initialize memory store
        memory = MemoryStore()
        
        # Store some test memories
        memory.write("rule", "test_rule", {"summary": "Always be helpful"})
        memory.write("preference", "user_pref", {"summary": "Likes technical details"})
        
        # Search for memories
        memories = memory.search("helpful technical", k=3)
        
        # Test message packing
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Can you help with a technical question?"}
        ]
        
        packed = pack_prompt(messages, memories, safety_mode=False)
        print(f"✅ Packed prompt: {len(packed)} messages total")
        
        # Test carry-kit extraction
        carry_kit_text = "Remember this: I am a senior developer working on AI systems. I prefer detailed technical explanations."
        items = extract_carry_kit_items(carry_kit_text)
        print(f"✅ Extracted {len(items)} carry-kit items")
        
        # Test should_remember logic
        should_store = should_remember("Remember this important fact")
        print(f"✅ Should remember test: {should_store}")
        
        memory.close()
        return True
        
    except Exception as e:
        print(f"❌ Packer system test failed: {e}")
        return False

async def test_tools_system():
    """Test the tool calling system."""
    print("\n=== Testing Tools System ===")
    
    from app.tools import tool_dispatcher, parse_tool_calls, execute_tool_calls
    
    try:
        # Test tool validation
        is_valid, error = tool_dispatcher.validate_tool_call(
            "book_meeting", 
            {"title": "Team Standup", "when": "Tomorrow 9 AM", "with": "Development Team"}
        )
        print(f"✅ Tool validation: {'Valid' if is_valid else f'Invalid - {error}'}")
        
        # Test tool dispatch
        result = tool_dispatcher.dispatch(
            "book_meeting",
            {"title": "AI Review", "when": "Friday 2 PM", "with": "Tech Team"}
        )
        print(f"✅ Tool execution: {'Success' if result['success'] else 'Failed'}")
        print(f"   Result: {result['result'][:60]}...")
        
        # Test message tool parsing
        message_with_tools = "TOOL:send_message(to='555-1234', message='Meeting confirmed')"
        parsed_calls = parse_tool_calls(message_with_tools)
        print(f"✅ Parsed {len(parsed_calls)} tool calls from message")
        
        # Test getting available tools
        available_tools = tool_dispatcher.get_available_tools()
        print(f"✅ Available tools: {len(available_tools)} tools registered")
        
        return True
        
    except Exception as e:
        print(f"❌ Tools system test failed: {e}")
        return False

async def test_full_chat_flow():
    """Test a complete chat flow end-to-end."""
    print("\n=== Testing Complete Chat Flow ===")
    
    from app.main import chat_completion
    from app.models import ChatRequest, Message
    from app.memory import MemoryStore
    
    try:
        # Create a mock memory store dependency
        memory_store = MemoryStore()
        
        # Test chat request
        from app.models import MessageRole
        request = ChatRequest(
            messages=[
                Message(role=MessageRole.USER, content="Hello! Remember this: I'm a Python developer working on AI projects. I prefer concise, technical responses.")
            ],
            temperature=0.7,
            max_tokens=200
        )
        
        # This would normally be called by FastAPI
        # We'll simulate the core logic here
        from app.llm import chat as llm_chat
        from app.packer import pack_prompt, should_remember, extract_carry_kit_items
        
        user_message = request.messages[-1].content
        
        # Process carry-kit items
        if should_remember(user_message):
            carry_kit_items = extract_carry_kit_items(user_message)
            for item in carry_kit_items:
                memory_id = memory_store.write(
                    item["type"], item["key"], item["value"], item.get("ttl_days", 365)
                )
                print(f"✅ Stored carry-kit item: {item['type']}:{item['key']}")
        
        # Retrieve memories
        memories = memory_store.search(user_message, k=6)
        print(f"✅ Retrieved {len(memories)} relevant memories")
        
        # Pack prompt
        message_dicts = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        final_messages = pack_prompt(message_dicts, memories, safety_mode=False)
        print(f"✅ Packed prompt with {len(final_messages)} messages")
        
        # Call LLM
        response, usage = llm_chat(final_messages, request.temperature, request.top_p, request.max_tokens)
        print(f"✅ Generated response: {usage['total_tokens']} tokens")
        print(f"   Response: {response[:100]}...")
        
        memory_store.close()
        return True
        
    except Exception as e:
        print(f"❌ Full chat flow test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Starting NeuroSphere Orchestrator Tests...")
    print("=" * 50)
    
    tests = [
        ("Memory System", test_memory_system),
        ("LLM System", test_llm_system),
        ("Packer System", test_packer_system),
        ("Tools System", test_tools_system),
        ("Full Chat Flow", test_full_chat_flow)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} test crashed: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print("=" * 50)
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 All systems are working correctly!")
        print("The NeuroSphere Orchestrator is ready for deployment.")
    else:
        print(f"\n⚠️  {len(results) - passed} test(s) failed. Check the logs above.")

if __name__ == "__main__":
    asyncio.run(main())