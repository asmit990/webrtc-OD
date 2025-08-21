# WebRTC Real-time Object Detection System

A high-performance real-time object detection system using WebRTC for phone-to-browser video streaming and YOLOv5n for object detection. Supports both client-side WASM inference and server-side processing.

## 🎯 Quick Start (One Command)

```bash
# Start in WASM mode (default, low-resource)
./start.sh

# Start in server mode with GPU/CPU acceleration
./start.sh --mode=server

# Start with public access via ngrok
./start.sh --ngrok
```

**Alternative: Docker**
```bash
docker-compose up --build
```

## 📱 Phone Connection

1. Start the system: `./start.sh`
2. Open http://localhost:3000 on your desktop browser
3. Scan the displayed QR code with your phone
4. Grant camera permission on your phone
5. Point camera at objects and watch real-time overlays on desktop

## 🏗️ Architecture

### Two Operating Modes

**WASM Mode (Default - Low Resource)**
- Client-side inference using ONNX.js
- Runs on modest laptops (4GB RAM, integrated GPU)
- 320x240 input resolution, 10-15 FPS
- No server-side GPU required

**Server Mode (High Performance)**
- Server-side inference using ONNX Runtime
- Requires 8GB+ RAM, CPU/GPU acceleration
- 640x480 input resolution, 15-30 FPS
- Better accuracy and speed

### System Components

```
Phone (Camera) → WebRTC → Desktop Browser → Object Detection → Overlay Rendering
                    ↓
              WebSocket Signaling
                    ↓
          FastAPI Backend (Optional Inference)
```

## 📊 Performance Metrics

The system tracks and reports:
- **End-to-End Latency**: capture_ts → overlay_display_ts
- **Processing FPS**: Frames processed per second
- **P95/Median Latency**: Statistical latency analysis
- **Bandwidth Usage**: Uplink/downlink monitoring

### API Contract (Frame Alignment)

```json
{
  "frame_id": "unique_string",
  "capture_ts": 1690000000000,
  "recv_ts": 1690000000100,
  "inference_ts": 1690000000120,
  "detections": [
    {
      "label": "person",
      "score": 0.93,
      "xmin": 0.12,
      "ymin": 0.08,
      "xmax": 0.34,
      "ymax": 0.67
    }
  ]
}
```

## 🧪 Benchmarking

Run comprehensive performance benchmarks:

```bash
# 30-second benchmark in WASM mode
./bench/run_bench.sh --duration 30 --mode wasm

# 60-second benchmark in server mode
./bench/run_bench.sh --duration 60 --mode server --output server_metrics.json
```

Outputs `metrics.json` with complete performance data:
- Median & P95 end-to-end latency
- Processed FPS
- Bandwidth usage (uplink/downlink kbps)
- System information

## 🔧 Configuration

### Environment Variables

**.env files are pre-configured - do not modify URLs/ports**

**Backend (.env)**:
- `MONGO_URL`: MongoDB connection (auto-configured)
- `CORS_ORIGINS`: CORS allowed origins
- `DB_NAME`: Database name

**Frontend (.env)**:
- `REACT_APP_BACKEND_URL`: Backend API URL (auto-configured)

### Backpressure Policy

The system implements intelligent frame management:
- Fixed-length frame queue (max 5 frames)
- Always processes most recent frame
- Drops older frames under load
- Adaptive sampling reduces FPS when latency > 200ms
- Resolution scaling for performance (320x240 ↔ 640x480)

## 🚀 Deployment Options

### Local Development
```bash
./start.sh --mode=wasm
```

### Docker Production
```bash
docker-compose up --build
```

### Public Access (Ngrok)
```bash
./start.sh --ngrok
# Requires ngrok account and auth token
```

### Custom Deployment
The system supports:
- Kubernetes deployment (k8s manifests included)
- AWS/GCP cloud deployment
- Local network deployment

## 🎮 Usage Instructions

### Desktop (Host)
1. Start system: `./start.sh`
2. Open http://localhost:3000
3. Choose detection mode (WASM/Server)
4. Share QR code or URL with phone

### Phone (Camera)
1. Scan QR code or visit provided URL
2. Grant camera permissions
3. Point at objects for detection
4. View real-time results on desktop

### Metrics Export
1. Let system run for desired duration
2. Click "Export Metrics" button
3. Download `metrics.json` for analysis

## 🔍 Troubleshooting

### Connection Issues
- Ensure same WiFi network for phone/desktop
- Use `--ngrok` flag for public access
- Check firewall settings (ports 3000, 8001)

### Performance Issues
- Switch to WASM mode for low-resource systems
- Reduce resolution: 320x240 for performance
- Lower FPS target: 10-12 FPS for stability
- Ensure good lighting for better detection

### Browser Issues
- Use Chrome (Android) or Safari (iOS)
- Enable camera permissions
- Check `chrome://webrtc-internals/` for debug info

### Model Loading
- Server mode downloads YOLOv5n automatically
- WASM mode uses embedded model
- Check logs for download/loading errors

## 📈 Performance Expectations

### WASM Mode (Low Resource)
- **Hardware**: 4GB RAM, integrated GPU
- **Latency**: 80-150ms median E2E
- **FPS**: 10-15 processed FPS
- **CPU**: 30-50% usage

### Server Mode (High Performance)
- **Hardware**: 8GB+ RAM, dedicated GPU
- **Latency**: 40-80ms median E2E
- **FPS**: 20-30 processed FPS
- **CPU**: 20-40% usage

## 🛠️ Development

### Project Structure
```
/app/
├── backend/           # FastAPI server
│   ├── server.py      # Main application
│   └── requirements.txt
├── frontend/          # React application
│   ├── src/App.js     # Main component
│   └── package.json
├── bench/             # Benchmarking tools
├── docker/            # Docker configuration
├── models/            # ONNX model storage
├── start.sh           # Main startup script
├── stop.sh            # Shutdown script
└── docker-compose.yml # Container orchestration
```

### Adding Custom Models
1. Place ONNX model in `models/` directory
2. Update `YOLOv5Detector` class in `server.py`
3. Modify WASM worker for client-side models
4. Update model path configuration

### Extending Detection Classes
Modify `class_names` array in `YOLOv5Detector` class for custom object classes.

## 🏆 Performance Optimizations

### Network Optimizations
- Frame compression (JPEG quality: 0.7)
- Adaptive bitrate based on latency
- WebRTC STUN/TURN servers for NAT traversal
- Connection quality monitoring

### Processing Optimizations
- Multi-threaded inference (ThreadPoolExecutor)
- Frame skipping under load
- Resolution scaling (320x240 ↔ 640x480)
- Confidence threshold tuning (0.25 default)

### Memory Management
- Bounded frame queues
- Automatic garbage collection
- Memory leak prevention
- Resource cleanup on disconnect

## 📄 License

MIT License - See LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 🆘 Support

For issues and questions:
1. Check troubleshooting section above
2. Review logs in `logs/` directory
3. Check browser developer console
4. Open GitHub issue with system details

---

**Next Improvement**: Implement adaptive quality scaling based on network conditions and device capabilities for optimal performance across all devices.# webrtc-OD
# webrtc-OD
