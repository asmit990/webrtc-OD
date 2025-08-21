#!/bin/bash

# WebRTC Object Detection System Startup Script
# Supports: MODE=wasm|server, --ngrok flag

set -e

# Default values
MODE="${MODE:-wasm}"
NGROK_ENABLED="${NGROK_ENABLED:-false}"
USE_NGROK=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode=*)
            MODE="${1#*=}"
            shift
            ;;
        --ngrok)
            USE_NGROK=true
            NGROK_ENABLED=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--mode=wasm|server] [--ngrok]"
            echo ""
            echo "Options:"
            echo "  --mode=wasm    Use WASM client-side inference (default, low-resource)"
            echo "  --mode=server  Use server-side ONNX inference"
            echo "  --ngrok        Enable ngrok for public access"
            echo "  --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                          # Start in WASM mode"
            echo "  $0 --mode=server           # Start in server mode"
            echo "  $0 --mode=wasm --ngrok     # Start with public access"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting WebRTC Object Detection System${NC}"
echo -e "${BLUE}================================================${NC}"
echo -e "Mode: ${GREEN}$MODE${NC}"
echo -e "Ngrok: ${GREEN}$NGROK_ENABLED${NC}"
echo ""

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo -e "${YELLOW}📦 Running in Docker container${NC}"
    exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
    exit 0
fi

# Native execution
echo -e "${YELLOW}🔧 Setting up native environment${NC}"

# Create necessary directories
mkdir -p models logs bench

# Check dependencies
echo -e "${BLUE}Checking dependencies...${NC}"

# Check Python dependencies
if ! python3 -c "import fastapi, motor, cv2, numpy" 2>/dev/null; then
    echo -e "${RED}❌ Missing Python dependencies. Installing...${NC}"
    if [ -f backend/requirements.txt ]; then
        pip install -r backend/requirements.txt
    else
        echo -e "${RED}❌ backend/requirements.txt not found${NC}"
        exit 1
    fi
fi

# Check Node.js dependencies
if [ ! -d frontend/node_modules ]; then
    echo -e "${YELLOW}📦 Installing Node.js dependencies...${NC}"
    cd frontend
    if command -v yarn &> /dev/null; then
        yarn install
    else
        npm install
    fi
    cd ..
fi

# Download YOLOv5n model if in server mode and model doesn't exist
if [ "$MODE" = "server" ] && [ ! -f models/yolov5n.onnx ]; then
    echo -e "${YELLOW}📥 Downloading YOLOv5n ONNX model...${NC}"
    wget -O models/yolov5n.onnx https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5n.onnx || {
        echo -e "${RED}❌ Failed to download YOLOv5n model. Creating placeholder...${NC}"
        echo "# YOLOv5n ONNX model placeholder" > models/yolov5n.onnx
    }
fi

# Set environment variables
export MODE="$MODE"
export PYTHONPATH="$(pwd)/backend"
export MONGO_URL="${MONGO_URL:-mongodb://localhost:27017/webrtc_detection}"
export CORS_ORIGINS="${CORS_ORIGINS:-*}"
export DB_NAME="${DB_NAME:-webrtc_detection}"
export REACT_APP_BACKEND_URL="http://localhost:8001"

# Start MongoDB if not running
if ! pgrep mongod > /dev/null; then
    echo -e "${YELLOW}🗃️  Starting MongoDB...${NC}"
    if command -v mongod &> /dev/null; then
        mongod --dbpath ./data --fork --logpath ./logs/mongodb.log --pidfilepath ./logs/mongodb.pid || {
            echo -e "${YELLOW}⚠️  MongoDB not available, using in-memory fallback${NC}"
        }
    else
        echo -e "${YELLOW}⚠️  MongoDB not installed, using in-memory fallback${NC}"
    fi
fi

# Setup ngrok if requested
if [ "$USE_NGROK" = true ]; then
    if command -v ngrok &> /dev/null; then
        echo -e "${YELLOW}🌐 Setting up ngrok tunnel...${NC}"
        
        # Start ngrok in background
        ngrok http 3000 --log=stdout > logs/ngrok.log &
        NGROK_PID=$!
        
        # Wait for ngrok to start
        sleep 3
        
        # Get public URL
        NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['tunnels'][0]['public_url'])
except:
    print('http://localhost:3000')
" 2>/dev/null || echo "http://localhost:3000")
        
        echo -e "${GREEN}🌐 Public URL: $NGROK_URL${NC}"
        echo -e "${GREEN}🌐 Phone join URL: $NGROK_URL/?role=phone${NC}"
        
        # Save ngrok PID for cleanup
        echo $NGROK_PID > logs/ngrok.pid
    else
        echo -e "${RED}❌ ngrok not installed. Download from https://ngrok.com/${NC}"
        echo -e "${YELLOW}⚠️  Continuing with local network only${NC}"
    fi
fi

# Start backend
echo -e "${BLUE}🔙 Starting FastAPI backend (port 8001)...${NC}"
cd backend
python3 -m uvicorn server:app --host 0.0.0.0 --port 8001 --log-level info > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > ../logs/backend.pid
cd ..

# Wait for backend to start
echo -e "${YELLOW}⏳ Waiting for backend to start...${NC}"
for i in {1..10}; do
    if curl -s http://localhost:8001/api/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend started successfully${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${RED}❌ Backend failed to start${NC}"
        cat logs/backend.log
        exit 1
    fi
    sleep 1
done

# Start frontend
echo -e "${BLUE}🎨 Starting React frontend (port 3000)...${NC}"
cd frontend
if command -v yarn &> /dev/null; then
    REACT_APP_BACKEND_URL=http://localhost:8001 yarn start > ../logs/frontend.log 2>&1 &
else
    REACT_APP_BACKEND_URL=http://localhost:8001 npm start > ../logs/frontend.log 2>&1 &
fi
FRONTEND_PID=$!
echo $FRONTEND_PID > ../logs/frontend.pid
cd ..

# Wait for frontend to start
echo -e "${YELLOW}⏳ Waiting for frontend to start...${NC}"
for i in {1..20}; do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Frontend started successfully${NC}"
        break
    fi
    if [ $i -eq 20 ]; then
        echo -e "${RED}❌ Frontend failed to start${NC}"
        cat logs/frontend.log
        exit 1
    fi
    sleep 1
done

# Display startup information
echo ""
echo -e "${GREEN}🎉 WebRTC Object Detection System is running!${NC}"
echo -e "${GREEN}=============================================${NC}"
echo -e "Desktop URL: ${BLUE}http://localhost:3000${NC}"
if [ "$USE_NGROK" = true ] && [ -n "$NGROK_URL" ]; then
    echo -e "Public URL:  ${BLUE}$NGROK_URL${NC}"
    echo -e "Phone URL:   ${BLUE}$NGROK_URL/?role=phone${NC}"
else
    echo -e "Phone URL:   ${BLUE}http://$(hostname -I | awk '{print $1}'):3000/?role=phone${NC}"
fi
echo -e "Backend API: ${BLUE}http://localhost:8001/api${NC}"
echo -e "Mode:        ${YELLOW}$MODE${NC}"
echo ""
echo -e "${YELLOW}📱 To connect your phone:${NC}"
echo "1. Open the desktop URL above"
echo "2. Scan the QR code with your phone"
echo "3. Grant camera permission"
echo "4. Point camera at objects"
echo ""
echo -e "${YELLOW}🔧 To stop the system:${NC}"
echo "Press Ctrl+C or run: ./stop.sh"
echo ""
echo -e "${YELLOW}📊 To run benchmarks:${NC}"
echo "./bench/run_bench.sh --duration 30 --mode $MODE"
echo ""

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down system...${NC}"
    
    # Kill processes
    [ -f logs/frontend.pid ] && kill $(cat logs/frontend.pid) 2>/dev/null || true
    [ -f logs/backend.pid ] && kill $(cat logs/backend.pid) 2>/dev/null || true
    [ -f logs/ngrok.pid ] && kill $(cat logs/ngrok.pid) 2>/dev/null || true
    [ -f logs/mongodb.pid ] && kill $(cat logs/mongodb.pid) 2>/dev/null || true
    
    # Remove pid files
    rm -f logs/*.pid
    
    echo -e "${GREEN}✅ System stopped${NC}"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Keep script running
echo -e "${BLUE}📈 Monitoring system... (Press Ctrl+C to stop)${NC}"
while true; do
    # Check if processes are still running
    if [ -f logs/backend.pid ] && ! ps -p $(cat logs/backend.pid) > /dev/null; then
        echo -e "${RED}❌ Backend process died${NC}"
        break
    fi
    
    if [ -f logs/frontend.pid ] && ! ps -p $(cat logs/frontend.pid) > /dev/null; then
        echo -e "${RED}❌ Frontend process died${NC}"
        break
    fi
    
    sleep 5
done

# If we get here, something crashed
echo -e "${RED}❌ System error detected${NC}"
cleanup