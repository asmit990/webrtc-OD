#!/bin/bash

# Stop WebRTC Object Detection System

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🛑 Stopping WebRTC Object Detection System...${NC}"

# Kill processes by PID files
if [ -f logs/frontend.pid ]; then
    PID=$(cat logs/frontend.pid)
    echo -e "${YELLOW}Stopping frontend (PID: $PID)...${NC}"
    kill $PID 2>/dev/null || echo -e "${RED}Frontend process not found${NC}"
    rm -f logs/frontend.pid
fi

if [ -f logs/backend.pid ]; then
    PID=$(cat logs/backend.pid)
    echo -e "${YELLOW}Stopping backend (PID: $PID)...${NC}"
    kill $PID 2>/dev/null || echo -e "${RED}Backend process not found${NC}"
    rm -f logs/backend.pid
fi

if [ -f logs/ngrok.pid ]; then
    PID=$(cat logs/ngrok.pid)
    echo -e "${YELLOW}Stopping ngrok (PID: $PID)...${NC}"
    kill $PID 2>/dev/null || echo -e "${RED}Ngrok process not found${NC}"
    rm -f logs/ngrok.pid
fi

if [ -f logs/mongodb.pid ]; then
    PID=$(cat logs/mongodb.pid)
    echo -e "${YELLOW}Stopping MongoDB (PID: $PID)...${NC}"
    kill $PID 2>/dev/null || echo -e "${RED}MongoDB process not found${NC}"
    rm -f logs/mongodb.pid
fi

# Kill any remaining processes
pkill -f "uvicorn server:app" 2>/dev/null || true
pkill -f "react-scripts start" 2>/dev/null || true
pkill -f "yarn start" 2>/dev/null || true
pkill -f "npm start" 2>/dev/null || true

echo -e "${GREEN}✅ System stopped${NC}"