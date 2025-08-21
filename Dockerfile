# Multi-stage Dockerfile for WebRTC Object Detection System
FROM node:18-slim as frontend-builder

# Install frontend dependencies
WORKDIR /app/frontend
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile

# Copy frontend source and build
COPY frontend/ ./
RUN yarn build

# Python backend stage
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    supervisor \
    nginx \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python requirements and install
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend code
COPY backend/ backend/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/build /app/frontend/build

# Copy configuration files
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/nginx.conf /etc/nginx/nginx.conf

# Create necessary directories
RUN mkdir -p /app/models /app/logs /var/log/supervisor

# Set environment variables
ENV PYTHONPATH=/app/backend
ENV MONGO_URL=mongodb://mongo:27017/webrtc_detection
ENV CORS_ORIGINS=*
ENV DB_NAME=webrtc_detection

# Create startup script
COPY docker/start.sh /start.sh
RUN chmod +x /start.sh

# Expose ports
EXPOSE 3000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/api/health || exit 1

# Start supervisor
CMD ["/start.sh"]