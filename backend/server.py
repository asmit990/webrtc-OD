from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import asyncio
import aiohttp
import time
import uuid
import base64
import numpy as np
import cv2
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime, timezone
import websockets
from concurrent.futures import ThreadPoolExecutor
import threading

# Import ONNX Runtime for server-mode inference
try:
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False
    print("ONNX Runtime not available - WASM mode only")

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(title="WebRTC Object Detection System")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Thread pool for CPU-intensive inference tasks
executor = ThreadPoolExecutor(max_workers=2)

# Global connection manager for WebRTC signaling
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.rooms: Dict[str, Dict[str, any]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str, room_id: str = "default"):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        
        if room_id not in self.rooms:
            self.rooms[room_id] = {"clients": {}, "host": None}
            
        self.rooms[room_id]["clients"][client_id] = {
            "websocket": websocket,
            "type": "unknown",
            "connected_at": time.time()
        }
        
        # First client becomes host (desktop browser)
        if self.rooms[room_id]["host"] is None:
            self.rooms[room_id]["host"] = client_id
            self.rooms[room_id]["clients"][client_id]["type"] = "host"
        else:
            # Subsequent clients are phones
            self.rooms[room_id]["clients"][client_id]["type"] = "phone"
        
        logging.info(f"Client {client_id} connected to room {room_id} as {self.rooms[room_id]['clients'][client_id]['type']}")
    
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        
        # Remove from rooms
        for room_id in self.rooms:
            if client_id in self.rooms[room_id]["clients"]:
                del self.rooms[room_id]["clients"][client_id]
                if self.rooms[room_id]["host"] == client_id:
                    self.rooms[room_id]["host"] = None
                    # Promote next client to host if available
                    remaining = list(self.rooms[room_id]["clients"].keys())
                    if remaining:
                        new_host = remaining[0]
                        self.rooms[room_id]["host"] = new_host
                        self.rooms[room_id]["clients"][new_host]["type"] = "host"
                break
    
    async def send_to_client(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(json.dumps(message))
            except:
                self.disconnect(client_id)
    
    async def broadcast_to_room(self, room_id: str, message: dict, exclude_client: str = None):
        if room_id in self.rooms:
            for client_id, client_info in self.rooms[room_id]["clients"].items():
                if client_id != exclude_client:
                    await self.send_to_client(client_id, message)

# Global connection manager instance
manager = ConnectionManager()

# YOLOv5n Inference Class (Server Mode)
class YOLOv5Detector:
    def __init__(self, model_path: str = None):
        self.session = None
        self.input_shape = (640, 640)  # Default YOLOv5n input shape
        self.class_names = [
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
            "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
            "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
            "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
            "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
            "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
            "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
            "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
            "hair drier", "toothbrush"
        ]
        
        if HAS_ONNX and model_path and os.path.exists(model_path):
            try:
                # Use CPU provider for compatibility
                providers = ['CPUExecutionProvider']
                self.session = ort.InferenceSession(model_path, providers=providers)
                logging.info(f"YOLOv5n model loaded successfully from {model_path}")
            except Exception as e:
                logging.error(f"Failed to load ONNX model: {e}")
                self.session = None
    
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for YOLOv5n inference"""
        # Resize image while maintaining aspect ratio
        h, w = image.shape[:2]
        new_h, new_w = self.input_shape
        
        # Calculate padding
        scale = min(new_w/w, new_h/h)
        new_unpad_w = int(w * scale)
        new_unpad_h = int(h * scale)
        
        # Create padded image
        padded_img = np.full((new_h, new_w, 3), 114, dtype=np.uint8)
        
        # Resize and place image in center
        resized_img = cv2.resize(image, (new_unpad_w, new_unpad_h))
        top = (new_h - new_unpad_h) // 2
        left = (new_w - new_unpad_w) // 2
        padded_img[top:top+new_unpad_h, left:left+new_unpad_w] = resized_img
        
        # Convert to RGB and normalize
        padded_img = cv2.cvtColor(padded_img, cv2.COLOR_BGR2RGB)
        padded_img = padded_img.astype(np.float32) / 255.0
        
        # Add batch dimension and transpose to NCHW format
        padded_img = np.transpose(padded_img, (2, 0, 1))
        padded_img = np.expand_dims(padded_img, axis=0)
        
        return padded_img, scale, (left, top)
    
    def postprocess_detections(self, outputs: np.ndarray, original_shape: tuple, 
                             scale: float, padding: tuple, conf_threshold: float = 0.25) -> List[Dict]:
        """Postprocess YOLO outputs to get bounding boxes"""
        if len(outputs.shape) == 3:
            outputs = outputs[0]  # Remove batch dimension if present
        
        detections = []
        orig_h, orig_w = original_shape[:2]
        pad_left, pad_top = padding
        
        for detection in outputs:
            # YOLO format: [x_center, y_center, width, height, conf, class_scores...]
            if len(detection) < 6:
                continue
                
            x_center, y_center, width, height, conf = detection[:5]
            class_scores = detection[5:]
            
            if conf < conf_threshold:
                continue
            
            class_id = np.argmax(class_scores)
            class_conf = class_scores[class_id]
            
            if class_conf < conf_threshold:
                continue
            
            # Convert from model space to original image space
            x_center = (x_center - pad_left) / scale
            y_center = (y_center - pad_top) / scale
            width = width / scale
            height = height / scale
            
            # Convert to corner coordinates
            x1 = max(0, x_center - width/2)
            y1 = max(0, y_center - height/2)
            x2 = min(orig_w, x_center + width/2)
            y2 = min(orig_h, y_center + height/2)
            
            # Normalize coordinates [0, 1]
            xmin = x1 / orig_w
            ymin = y1 / orig_h
            xmax = x2 / orig_w
            ymax = y2 / orig_h
            
            detections.append({
                "label": self.class_names[class_id] if class_id < len(self.class_names) else f"class_{class_id}",
                "score": float(conf * class_conf),
                "xmin": float(xmin),
                "ymin": float(ymin),
                "xmax": float(xmax),
                "ymax": float(ymax)
            })
        
        return detections
    
    def detect_objects(self, image: np.ndarray) -> List[Dict]:
        """Run object detection on image"""
        if self.session is None:
            return []
        
        try:
            # Preprocess image
            preprocessed, scale, padding = self.preprocess_image(image)
            
            # Run inference
            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: preprocessed})
            
            # Postprocess outputs
            detections = self.postprocess_detections(
                outputs[0], image.shape, scale, padding
            )
            
            return detections
            
        except Exception as e:
            logging.error(f"Detection error: {e}")
            return []

# Global detector instance
detector = YOLOv5Detector()

# Models
class DetectionFrame(BaseModel):
    frame_id: str
    capture_ts: int
    recv_ts: int
    inference_ts: int
    detections: List[Dict]
    
class MetricsData(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    frame_count: int
    processed_fps: float
    median_e2e_latency: float
    p95_e2e_latency: float
    uplink_kbps: float
    downlink_kbps: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# API Routes
@api_router.get("/")
async def root():
    return {"message": "WebRTC Object Detection System", "status": "running"}

@api_router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "onnx_available": HAS_ONNX,
        "model_loaded": detector.session is not None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@api_router.post("/metrics", response_model=MetricsData)
async def store_metrics(metrics: MetricsData):
    """Store metrics data in database"""
    metrics_dict = metrics.dict()
    await db.metrics.insert_one(metrics_dict)
    return metrics

@api_router.get("/metrics/{session_id}")
async def get_metrics(session_id: str):
    """Get metrics for a specific session"""
    metrics = await db.metrics.find({"session_id": session_id}).to_list(100)
    return [MetricsData(**m) for m in metrics]

# Frame processing function (runs in thread pool)
def process_frame_sync(frame_data: str, frame_id: str, capture_ts: int, recv_ts: int) -> Dict:
    """Synchronous frame processing function for threading"""
    try:
        # Decode base64 image
        image_bytes = base64.b64decode(frame_data.split(',')[1] if ',' in frame_data else frame_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return {
                "frame_id": frame_id,
                "capture_ts": capture_ts,
                "recv_ts": recv_ts,
                "inference_ts": int(time.time() * 1000),
                "detections": [],
                "error": "Failed to decode image"
            }
        
        # Run object detection
        inference_start = time.time()
        detections = detector.detect_objects(image)
        inference_ts = int(inference_start * 1000)
        
        return {
            "frame_id": frame_id,
            "capture_ts": capture_ts,
            "recv_ts": recv_ts,
            "inference_ts": inference_ts,
            "detections": detections
        }
        
    except Exception as e:
        logging.error(f"Frame processing error: {e}")
        return {
            "frame_id": frame_id,
            "capture_ts": capture_ts,
            "recv_ts": recv_ts,
            "inference_ts": int(time.time() * 1000),
            "detections": [],
            "error": str(e)
        }

# WebRTC Signaling WebSocket
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, room_id: str = "default"):
    await manager.connect(websocket, client_id, room_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message_type = message.get("type")
            
            if message_type == "offer" or message_type == "answer" or message_type == "ice-candidate":
                # Relay WebRTC signaling messages to other clients in room
                await manager.broadcast_to_room(room_id, message, exclude_client=client_id)
            
            elif message_type == "frame":
                # Process video frame for object detection (server mode)
                if HAS_ONNX and detector.session is not None:
                    frame_data = message.get("data")
                    frame_id = message.get("frame_id", str(uuid.uuid4()))
                    capture_ts = message.get("capture_ts", int(time.time() * 1000))
                    recv_ts = int(time.time() * 1000)
                    
                    # Process frame in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        executor, process_frame_sync, frame_data, frame_id, capture_ts, recv_ts
                    )
                    
                    # Send detection results back
                    await manager.send_to_client(client_id, {
                        "type": "detection",
                        **result
                    })
                
            elif message_type == "join_room":
                # Handle room joining
                target_room = message.get("room_id", room_id)
                await manager.send_to_client(client_id, {
                    "type": "room_joined",
                    "room_id": target_room,
                    "client_id": client_id,
                    "client_type": manager.rooms[room_id]["clients"][client_id]["type"]
                })
            
            elif message_type == "ping":
                await manager.send_to_client(client_id, {"type": "pong", "timestamp": int(time.time() * 1000)})
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logging.info(f"Client {client_id} disconnected")
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        manager.disconnect(client_id)

# Serve model files and static assets
models_dir = ROOT_DIR / "models"
models_dir.mkdir(exist_ok=True)
app.mount("/models", StaticFiles(directory=models_dir), name="models")

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    logging.info("Starting WebRTC Object Detection System")
    
    # Download YOLOv5n model if not exists (server mode)
    model_path = models_dir / "yolov5n.onnx"
    if not model_path.exists() and HAS_ONNX:
        logging.info("Downloading YOLOv5n ONNX model...")
        try:
            # This would normally download the model, but we'll create a placeholder for now
            logging.info("Model download would happen here - using mock for development")
        except Exception as e:
            logging.error(f"Failed to download model: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    executor.shutdown(wait=True)