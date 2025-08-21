#!/usr/bin/env python3
"""
Local frame processing test
"""

import asyncio
import websockets
import json
import time
import uuid
import base64
import cv2
import numpy as np

def create_test_image() -> str:
    """Create a test image as base64 string"""
    # Create a simple test image with some objects
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Draw some rectangles to simulate objects
    cv2.rectangle(img, (100, 100), (200, 200), (255, 0, 0), -1)  # Blue rectangle
    cv2.rectangle(img, (300, 200), (400, 350), (0, 255, 0), -1)  # Green rectangle
    cv2.circle(img, (500, 150), 50, (0, 0, 255), -1)  # Red circle
    
    # Encode to base64
    _, buffer = cv2.imencode('.jpg', img)
    img_base64 = base64.b64encode(buffer).decode('utf-8')
    return f"data:image/jpeg;base64,{img_base64}"

async def test_frame_processing():
    """Test frame processing locally"""
    client_id = f"frame_test_{int(time.time())}"
    ws_url = f"ws://localhost:8001/ws/{client_id}"
    
    try:
        print(f"Connecting to: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            print("✅ WebSocket connected successfully!")
            
            # Create test image
            test_image = create_test_image()
            print(f"Created test image: {len(test_image)} characters")
            
            # Send frame for processing
            frame_message = {
                "type": "frame",
                "data": test_image,
                "frame_id": str(uuid.uuid4()),
                "capture_ts": int(time.time() * 1000)
            }
            await websocket.send(json.dumps(frame_message))
            print("Sent frame for processing...")
            
            # Wait for detection results
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=15)
                data = json.loads(response)
                print(f"Received response: {data}")
                
                if data.get("type") == "detection":
                    if "frame_id" in data and "detections" in data:
                        detection_count = len(data["detections"])
                        print(f"✅ Frame processing successful! Detections: {detection_count}")
                        if detection_count > 0:
                            print("Sample detection:", data["detections"][0])
                        return True
                    else:
                        print(f"❌ Invalid detection response: {data}")
                else:
                    print(f"❌ Expected detection response, got: {data}")
            except asyncio.TimeoutError:
                print("❌ Timeout waiting for detection response")
                return False
                
    except Exception as e:
        print(f"❌ Frame processing test failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_frame_processing())
    print(f"Frame processing test: {'PASSED' if result else 'FAILED'}")