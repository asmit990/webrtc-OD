#!/bin/bash

# Docker container startup script
echo "🐳 Starting WebRTC Object Detection System in Docker..."

# Set environment variables
export PYTHONPATH=/app/backend
export NODE_ENV=production

# Create necessary directories
mkdir -p /app/models /app/logs /var/log/supervisor

# Download YOLOv5n model if in server mode
if [ "$MODE" = "server" ] && [ ! -f /app/models/yolov5n.onnx ]; then
    echo "📥 Downloading YOLOv5n ONNX model..."
    wget -O /app/models/yolov5n.onnx https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5n.onnx || {
        echo "⚠️ Failed to download model, creating placeholder"
        echo "# YOLOv5n ONNX placeholder" > /app/models/yolov5n.onnx
    }
fi

# Start services via supervisor
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf