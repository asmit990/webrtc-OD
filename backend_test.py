#!/usr/bin/env python3
"""
Comprehensive Backend Testing for WebRTC Object Detection System
Tests WebSocket signaling, frame processing, metrics, and API endpoints
"""

import asyncio
import websockets
import json
import requests
import base64
import time
import uuid
import cv2
import numpy as np
from datetime import datetime, timezone
import os
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "frontend" / ".env")

# Get backend URL from environment
BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://realtime-detect-2.preview.emergentagent.com')
API_BASE_URL = f"{BACKEND_URL}/api"
WS_BASE_URL = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://')

print(f"Testing backend at: {API_BASE_URL}")
print(f"WebSocket URL: {WS_BASE_URL}")

class BackendTester:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.test_results = {
            "health_check": False,
            "websocket_connection": False,
            "webrtc_signaling": False,
            "frame_processing": False,
            "metrics_storage": False,
            "metrics_retrieval": False,
            "error_handling": False
        }
        self.errors = []

    def log_error(self, test_name: str, error: str):
        """Log test errors"""
        self.errors.append(f"{test_name}: {error}")
        print(f"❌ {test_name} FAILED: {error}")

    def log_success(self, test_name: str, message: str = ""):
        """Log test success"""
        self.test_results[test_name] = True
        print(f"✅ {test_name} PASSED {message}")

    def create_test_image(self) -> str:
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

    def test_health_check(self):
        """Test the health check endpoint"""
        try:
            response = requests.get(f"{API_BASE_URL}/health", timeout=30)
            if response.status_code == 200:
                data = response.json()
                if "status" in data and "onnx_available" in data:
                    self.log_success("health_check", f"- Status: {data['status']}, ONNX: {data['onnx_available']}")
                    return True
                else:
                    self.log_error("health_check", f"Invalid response format: {data}")
            else:
                self.log_error("health_check", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_error("health_check", str(e))
        return False

    async def test_websocket_connection(self):
        """Test basic WebSocket connection"""
        client_id = f"test_client_{int(time.time())}"
        ws_url = f"{WS_BASE_URL}/ws/{client_id}"
        
        try:
            async with websockets.connect(ws_url) as websocket:
                # Test ping-pong
                ping_message = {"type": "ping", "timestamp": int(time.time() * 1000)}
                await websocket.send(json.dumps(ping_message))
                
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                data = json.loads(response)
                
                if data.get("type") == "pong":
                    self.log_success("websocket_connection", f"- Client ID: {client_id}")
                    return True
                else:
                    self.log_error("websocket_connection", f"Unexpected response: {data}")
        except Exception as e:
            self.log_error("websocket_connection", str(e))
        return False

    async def test_webrtc_signaling(self):
        """Test WebRTC signaling message relay"""
        client1_id = f"host_{int(time.time())}"
        client2_id = f"phone_{int(time.time())}"
        room_id = "test_room"
        
        try:
            # Connect two clients
            ws1_url = f"{WS_BASE_URL}/ws/{client1_id}?room_id={room_id}"
            ws2_url = f"{WS_BASE_URL}/ws/{client2_id}?room_id={room_id}"
            
            async with websockets.connect(ws1_url) as ws1, \
                       websockets.connect(ws2_url) as ws2:
                
                # Client 1 sends offer
                offer_message = {
                    "type": "offer",
                    "sdp": "mock_sdp_offer_data",
                    "from": client1_id
                }
                await ws1.send(json.dumps(offer_message))
                
                # Client 2 should receive the offer
                response = await asyncio.wait_for(ws2.recv(), timeout=10)
                data = json.loads(response)
                
                if data.get("type") == "offer" and data.get("sdp") == "mock_sdp_offer_data":
                    # Client 2 sends answer
                    answer_message = {
                        "type": "answer",
                        "sdp": "mock_sdp_answer_data",
                        "from": client2_id
                    }
                    await ws2.send(json.dumps(answer_message))
                    
                    # Client 1 should receive the answer
                    response = await asyncio.wait_for(ws1.recv(), timeout=10)
                    data = json.loads(response)
                    
                    if data.get("type") == "answer" and data.get("sdp") == "mock_sdp_answer_data":
                        self.log_success("webrtc_signaling", f"- Room: {room_id}")
                        return True
                    else:
                        self.log_error("webrtc_signaling", f"Answer not received correctly: {data}")
                else:
                    self.log_error("webrtc_signaling", f"Offer not received correctly: {data}")
                    
        except Exception as e:
            self.log_error("webrtc_signaling", str(e))
        return False

    async def test_frame_processing(self):
        """Test frame processing and object detection"""
        client_id = f"frame_test_{int(time.time())}"
        ws_url = f"{WS_BASE_URL}/ws/{client_id}"
        
        try:
            async with websockets.connect(ws_url) as websocket:
                # Create test image
                test_image = self.create_test_image()
                
                # Send frame for processing
                frame_message = {
                    "type": "frame",
                    "data": test_image,
                    "frame_id": str(uuid.uuid4()),
                    "capture_ts": int(time.time() * 1000)
                }
                await websocket.send(json.dumps(frame_message))
                
                # Wait for detection results
                response = await asyncio.wait_for(websocket.recv(), timeout=20)
                data = json.loads(response)
                
                if data.get("type") == "detection":
                    if "frame_id" in data and "detections" in data:
                        detection_count = len(data["detections"])
                        self.log_success("frame_processing", f"- Detections: {detection_count}")
                        return True
                    else:
                        self.log_error("frame_processing", f"Invalid detection response: {data}")
                else:
                    self.log_error("frame_processing", f"Expected detection response, got: {data}")
                    
        except Exception as e:
            self.log_error("frame_processing", str(e))
        return False

    def test_metrics_storage(self):
        """Test metrics storage endpoint"""
        try:
            metrics_data = {
                "session_id": self.session_id,
                "frame_count": 100,
                "processed_fps": 15.5,
                "median_e2e_latency": 120.5,
                "p95_e2e_latency": 250.0,
                "uplink_kbps": 1500.0,
                "downlink_kbps": 800.0
            }
            
            response = requests.post(
                f"{API_BASE_URL}/metrics",
                json=metrics_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if "id" in data and data["session_id"] == self.session_id:
                    self.log_success("metrics_storage", f"- Session: {self.session_id}")
                    return True
                else:
                    self.log_error("metrics_storage", f"Invalid response: {data}")
            else:
                self.log_error("metrics_storage", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_error("metrics_storage", str(e))
        return False

    def test_metrics_retrieval(self):
        """Test metrics retrieval endpoint"""
        try:
            response = requests.get(f"{API_BASE_URL}/metrics/{self.session_id}", timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    metric = data[0]
                    if metric.get("session_id") == self.session_id:
                        self.log_success("metrics_retrieval", f"- Found {len(data)} metrics")
                        return True
                    else:
                        self.log_error("metrics_retrieval", f"Session ID mismatch: {metric}")
                else:
                    self.log_error("metrics_retrieval", f"No metrics found for session: {self.session_id}")
            else:
                self.log_error("metrics_retrieval", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_error("metrics_retrieval", str(e))
        return False

    async def test_error_handling(self):
        """Test error handling for malformed requests"""
        client_id = f"error_test_{int(time.time())}"
        ws_url = f"{WS_BASE_URL}/ws/{client_id}"
        
        try:
            async with websockets.connect(ws_url) as websocket:
                # Send malformed JSON
                await websocket.send("invalid_json")
                
                # Connection should remain open (graceful error handling)
                # Send valid ping to verify connection is still alive
                ping_message = {"type": "ping"}
                await websocket.send(json.dumps(ping_message))
                
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                data = json.loads(response)
                
                if data.get("type") == "pong":
                    self.log_success("error_handling", "- Graceful error handling verified")
                    return True
                else:
                    self.log_error("error_handling", f"Connection not recovered after error: {data}")
                    
        except Exception as e:
            self.log_error("error_handling", str(e))
        return False

    async def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting Backend Tests for WebRTC Object Detection System")
        print("=" * 60)
        
        # Test 1: Health Check
        print("\n1. Testing Health Check Endpoint...")
        self.test_results["health_check"] = self.test_health_check()
        
        # Test 2: WebSocket Connection
        print("\n2. Testing WebSocket Connection...")
        self.test_results["websocket_connection"] = await self.test_websocket_connection()
        
        # Test 3: WebRTC Signaling
        print("\n3. Testing WebRTC Signaling...")
        self.test_results["webrtc_signaling"] = await self.test_webrtc_signaling()
        
        # Test 4: Frame Processing
        print("\n4. Testing Frame Processing...")
        self.test_results["frame_processing"] = await self.test_frame_processing()
        
        # Test 5: Metrics Storage
        print("\n5. Testing Metrics Storage...")
        self.test_results["metrics_storage"] = self.test_metrics_storage()
        
        # Test 6: Metrics Retrieval
        print("\n6. Testing Metrics Retrieval...")
        self.test_results["metrics_retrieval"] = self.test_metrics_retrieval()
        
        # Test 7: Error Handling
        print("\n7. Testing Error Handling...")
        self.test_results["error_handling"] = await self.test_error_handling()
        
        # Print Results
        self.print_results()

    def print_results(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 60)
        print("🎯 BACKEND TEST RESULTS")
        print("=" * 60)
        
        passed = sum(1 for result in self.test_results.values() if result)
        total = len(self.test_results)
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name.replace('_', ' ').title()}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if self.errors:
            print(f"\n🚨 ERRORS ENCOUNTERED ({len(self.errors)}):")
            for error in self.errors:
                print(f"  • {error}")
        
        print("\n" + "=" * 60)
        
        # Return overall success
        return passed == total

async def main():
    """Main test runner"""
    tester = BackendTester()
    success = await tester.run_all_tests()
    
    if success:
        print("🎉 All backend tests passed!")
        return 0
    else:
        print("💥 Some backend tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)