#!/usr/bin/env python3
"""
Local WebSocket test to verify backend functionality
"""

import asyncio
import websockets
import json
import time
import uuid

async def test_local_websocket():
    """Test WebSocket connection locally"""
    client_id = f"local_test_{int(time.time())}"
    ws_url = f"ws://localhost:8001/ws/{client_id}"
    
    try:
        print(f"Connecting to: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            print("✅ WebSocket connected successfully!")
            
            # Test ping-pong
            ping_message = {"type": "ping", "timestamp": int(time.time() * 1000)}
            await websocket.send(json.dumps(ping_message))
            print(f"Sent: {ping_message}")
            
            response = await asyncio.wait_for(websocket.recv(), timeout=5)
            data = json.loads(response)
            print(f"Received: {data}")
            
            if data.get("type") == "pong":
                print("✅ Ping-pong test passed!")
                return True
            else:
                print(f"❌ Unexpected response: {data}")
                
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_local_websocket())
    print(f"Local WebSocket test: {'PASSED' if result else 'FAILED'}")