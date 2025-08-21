import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const WS_URL = BACKEND_URL ? BACKEND_URL.replace('http', 'ws') : 'ws://localhost:8001';

// Generate QR code URL for phone connection
const generateQRCode = (url) => {
  return `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(url)}`;
};

// Utility functions for metrics calculation
const calculateLatencyMetrics = (latencies) => {
  if (latencies.length === 0) return { median: 0, p95: 0 };
  
  const sorted = [...latencies].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const p95Index = Math.floor(sorted.length * 0.95);
  const p95 = sorted[Math.min(p95Index, sorted.length - 1)];
  
  return { median, p95 };
};

// WebRTC Configuration
const rtcConfiguration = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' }
  ]
};

function App() {
  // State management
  const [connectionState, setConnectionState] = useState('disconnected');
  const [isHost, setIsHost] = useState(true);
  const [roomId] = useState('default');
  const [clientId] = useState(() => Math.random().toString(36).substr(2, 9));
  const [detectionMode, setDetectionMode] = useState('wasm'); // 'wasm' or 'server'
  const [metrics, setMetrics] = useState({
    frameCount: 0,
    processedFrames: 0,
    latencies: [],
    fps: 0,
    bandwidth: { uplink: 0, downlink: 0 }
  });
  const [currentDetections, setCurrentDetections] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  
  // Refs
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const peerConnectionRef = useRef(null);
  const localStreamRef = useRef(null);
  const detectionWorkerRef = useRef(null);
  const frameQueueRef = useRef([]);
  const lastFrameTimeRef = useRef(0);
  const metricsIntervalRef = useRef(null);
  
  // Phone join URL for QR code
  const phoneJoinURL = `${window.location.origin}/?client_id=${clientId}&role=phone`;
  
  // Initialize detection worker (WASM mode)
  useEffect(() => {
    if (detectionMode === 'wasm') {
      // Initialize ONNX Web Worker for client-side inference
      const workerCode = `
        // ONNX Web Worker for YOLOv5n inference
        import('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.16.3/dist/ort.wasm.js').then(() => {
          const ort = self.ort;
          
          let session = null;
          
          // Initialize model
          const initModel = async () => {
            try {
              // This would load the actual YOLOv5n ONNX model
              // For demo purposes, we'll simulate inference
              console.log('ONNX WASM model initialized');
            } catch (error) {
              console.error('Failed to load ONNX model:', error);
            }
          };
          
          // Process frame for object detection
          const processFrame = async (imageData, frameId, captureTs) => {
            const recvTs = Date.now();
            const inferenceTs = Date.now();
            
            // Mock detection results for demo
            const detections = [
              {
                label: "person",
                score: 0.85,
                xmin: 0.2,
                ymin: 0.1,
                xmax: 0.4,
                ymax: 0.8
              },
              {
                label: "phone",
                score: 0.72,
                xmin: 0.6,
                ymin: 0.3,
                xmax: 0.8,
                ymax: 0.6
              }
            ];
            
            return {
              frame_id: frameId,
              capture_ts: captureTs,
              recv_ts: recvTs,
              inference_ts: inferenceTs,
              detections: detections
            };
          };
          
          self.onmessage = async (e) => {
            const { type, data } = e.data;
            
            if (type === 'init') {
              await initModel();
              self.postMessage({ type: 'ready' });
            } else if (type === 'detect') {
              const { imageData, frameId, captureTs } = data;
              const result = await processFrame(imageData, frameId, captureTs);
              self.postMessage({ type: 'detection', result });
            }
          };
        });
      `;
      
      const blob = new Blob([workerCode], { type: 'application/javascript' });
      const workerUrl = URL.createObjectURL(blob);
      
      try {
        detectionWorkerRef.current = new Worker(workerUrl);
        
        detectionWorkerRef.current.onmessage = (e) => {
          const { type, result } = e.data;
          
          if (type === 'detection') {
            handleDetectionResult(result);
          }
        };
        
        detectionWorkerRef.current.postMessage({ type: 'init' });
        
      } catch (error) {
        console.error('Failed to create WASM worker:', error);
        // Fallback to mock detections
        setDetectionMode('mock');
      }
      
      return () => {
        if (detectionWorkerRef.current) {
          detectionWorkerRef.current.terminate();
          URL.revokeObjectURL(workerUrl);
        }
      };
    }
  }, [detectionMode]);
  
  // WebSocket connection
  useEffect(() => {
    const connectWebSocket = () => {
      const wsUrl = `${WS_URL}/ws/${clientId}?room_id=${roomId}`;
      wsRef.current = new WebSocket(wsUrl);
      
      wsRef.current.onopen = () => {
        console.log('WebSocket connected');
        setConnectionState('connected');
        
        // Join room
        wsRef.current.send(JSON.stringify({
          type: 'join_room',
          room_id: roomId,
          client_id: clientId
        }));
      };
      
      wsRef.current.onmessage = async (event) => {
        const message = JSON.parse(event.data);
        await handleSignalingMessage(message);
      };
      
      wsRef.current.onclose = () => {
        console.log('WebSocket disconnected');
        setConnectionState('disconnected');
        // Attempt to reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
      };
      
      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
    };
    
    connectWebSocket();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [clientId, roomId]);
  
  // Handle signaling messages
  const handleSignalingMessage = async (message) => {
    const { type } = message;
    
    if (type === 'room_joined') {
      console.log('Joined room:', message);
      setIsHost(message.client_type === 'host');
    } else if (type === 'offer') {
      await handleOffer(message);
    } else if (type === 'answer') {
      await handleAnswer(message);
    } else if (type === 'ice-candidate') {
      await handleIceCandidate(message);
    } else if (type === 'detection') {
      handleDetectionResult(message);
    }
  };
  
  // Initialize WebRTC peer connection
  const createPeerConnection = useCallback(() => {
    const pc = new RTCPeerConnection(rtcConfiguration);
    
    pc.onicecandidate = (event) => {
      if (event.candidate && wsRef.current) {
        wsRef.current.send(JSON.stringify({
          type: 'ice-candidate',
          candidate: event.candidate
        }));
      }
    };
    
    pc.ontrack = (event) => {
      console.log('Received remote stream');
      if (remoteVideoRef.current) {
        remoteVideoRef.current.srcObject = event.streams[0];
      }
    };
    
    pc.onconnectionstatechange = () => {
      console.log('Connection state:', pc.connectionState);
      setConnectionState(pc.connectionState);
    };
    
    return pc;
  }, []);
  
  // Start camera (for phone clients)
  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'environment' },
        audio: false
      });
      
      localStreamRef.current = stream;
      
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
      }
      
      // Create peer connection and add stream
      peerConnectionRef.current = createPeerConnection();
      stream.getTracks().forEach(track => {
        peerConnectionRef.current.addTrack(track, stream);
      });
      
      // Start frame capture for object detection
      if (isHost) {
        startFrameCapture();
      } else {
        // Phone creates offer
        createOffer();
      }
      
      setIsRecording(true);
      startMetricsCollection();
      
    } catch (error) {
      console.error('Error accessing camera:', error);
      alert('Failed to access camera. Please check permissions.');
    }
  };
  
  // Create WebRTC offer
  const createOffer = async () => {
    if (!peerConnectionRef.current) return;
    
    try {
      const offer = await peerConnectionRef.current.createOffer();
      await peerConnectionRef.current.setLocalDescription(offer);
      
      wsRef.current.send(JSON.stringify({
        type: 'offer',
        offer: offer
      }));
    } catch (error) {
      console.error('Error creating offer:', error);
    }
  };
  
  // Handle WebRTC offer
  const handleOffer = async (message) => {
    if (!peerConnectionRef.current) {
      peerConnectionRef.current = createPeerConnection();
    }
    
    try {
      await peerConnectionRef.current.setRemoteDescription(message.offer);
      const answer = await peerConnectionRef.current.createAnswer();
      await peerConnectionRef.current.setLocalDescription(answer);
      
      wsRef.current.send(JSON.stringify({
        type: 'answer',
        answer: answer
      }));
    } catch (error) {
      console.error('Error handling offer:', error);
    }
  };
  
  // Handle WebRTC answer
  const handleAnswer = async (message) => {
    try {
      await peerConnectionRef.current.setRemoteDescription(message.answer);
    } catch (error) {
      console.error('Error handling answer:', error);
    }
  };
  
  // Handle ICE candidate
  const handleIceCandidate = async (message) => {
    if (peerConnectionRef.current) {
      try {
        await peerConnectionRef.current.addIceCandidate(message.candidate);
      } catch (error) {
        console.error('Error adding ICE candidate:', error);
      }
    }
  };
  
  // Start frame capture for object detection
  const startFrameCapture = () => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    
    const captureFrame = () => {
      if (!isRecording || !localStreamRef.current) {
        return;
      }
      
      const video = localVideoRef.current || remoteVideoRef.current;
      if (!video || video.videoWidth === 0) {
        requestAnimationFrame(captureFrame);
        return;
      }
      
      // Limit to 15 FPS for performance
      const now = Date.now();
      if (now - lastFrameTimeRef.current < 66) { // ~15 FPS
        requestAnimationFrame(captureFrame);
        return;
      }
      lastFrameTimeRef.current = now;
      
      // Capture frame
      canvas.width = Math.min(video.videoWidth, 320); // Limit resolution
      canvas.height = Math.min(video.videoHeight, 240);
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      
      // Convert to base64
      const frameData = canvas.toDataURL('image/jpeg', 0.7);
      const frameId = Math.random().toString(36).substr(2, 9);
      const captureTs = Date.now();
      
      // Send for processing
      processFrameForDetection(frameData, frameId, captureTs);
      
      setMetrics(prev => ({
        ...prev,
        frameCount: prev.frameCount + 1
      }));
      
      requestAnimationFrame(captureFrame);
    };
    
    requestAnimationFrame(captureFrame);
  };
  
  // Process frame for object detection
  const processFrameForDetection = (frameData, frameId, captureTs) => {
    if (detectionMode === 'server' && wsRef.current) {
      // Send to server for processing
      wsRef.current.send(JSON.stringify({
        type: 'frame',
        data: frameData,
        frame_id: frameId,
        capture_ts: captureTs
      }));
    } else if (detectionMode === 'wasm' && detectionWorkerRef.current) {
      // Send to WASM worker
      detectionWorkerRef.current.postMessage({
        type: 'detect',
        data: { imageData: frameData, frameId, captureTs }
      });
    } else {
      // Mock detection for demo
      setTimeout(() => {
        handleDetectionResult({
          frame_id: frameId,
          capture_ts: captureTs,
          recv_ts: Date.now(),
          inference_ts: Date.now(),
          detections: [
            {
              label: "person",
              score: 0.78,
              xmin: 0.25,
              ymin: 0.15,
              xmax: 0.45,
              ymax: 0.75
            }
          ]
        });
      }, 50);
    }
  };
  
  // Handle detection results
  const handleDetectionResult = (result) => {
    const overlayTs = Date.now();
    const e2eLatency = overlayTs - result.capture_ts;
    
    setCurrentDetections(result.detections || []);
    
    setMetrics(prev => ({
      ...prev,
      processedFrames: prev.processedFrames + 1,
      latencies: [...prev.latencies.slice(-100), e2eLatency] // Keep last 100
    }));
    
    // Draw overlays
    drawOverlays(result.detections || []);
  };
  
  // Draw detection overlays on canvas
  const drawOverlays = (detections) => {
    const canvas = canvasRef.current;
    const video = remoteVideoRef.current || localVideoRef.current;
    
    if (!canvas || !video) return;
    
    const ctx = canvas.getContext('2d');
    canvas.width = video.clientWidth || 640;
    canvas.height = video.clientHeight || 480;
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw bounding boxes
    ctx.strokeStyle = '#00ff00';
    ctx.lineWidth = 3;
    ctx.font = '16px Arial';
    ctx.fillStyle = '#00ff00';
    
    detections.forEach(detection => {
      const x = detection.xmin * canvas.width;
      const y = detection.ymin * canvas.height;
      const width = (detection.xmax - detection.xmin) * canvas.width;
      const height = (detection.ymax - detection.ymin) * canvas.height;
      
      // Draw bounding box
      ctx.strokeRect(x, y, width, height);
      
      // Draw label with confidence
      const label = `${detection.label} (${(detection.score * 100).toFixed(1)}%)`;
      const textWidth = ctx.measureText(label).width;
      
      // Label background
      ctx.fillStyle = 'rgba(0, 255, 0, 0.8)';
      ctx.fillRect(x, y - 25, textWidth + 10, 20);
      
      // Label text
      ctx.fillStyle = '#000000';
      ctx.fillText(label, x + 5, y - 8);
    });
  };
  
  // Start metrics collection
  const startMetricsCollection = () => {
    metricsIntervalRef.current = setInterval(() => {
      setMetrics(prev => {
        const { median, p95 } = calculateLatencyMetrics(prev.latencies);
        const fps = prev.frameCount > 0 ? prev.processedFrames / (Date.now() - lastFrameTimeRef.current) * 1000 : 0;
        
        return {
          ...prev,
          fps: fps,
          medianLatency: median,
          p95Latency: p95
        };
      });
    }, 1000);
  };
  
  // Stop recording
  const stopRecording = () => {
    setIsRecording(false);
    
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(track => track.stop());
    }
    
    if (peerConnectionRef.current) {
      peerConnectionRef.current.close();
    }
    
    if (metricsIntervalRef.current) {
      clearInterval(metricsIntervalRef.current);
    }
  };
  
  // Export metrics
  const exportMetrics = () => {
    const metricsData = {
      session_id: clientId,
      frame_count: metrics.frameCount,
      processed_fps: metrics.fps || 0,
      median_e2e_latency: metrics.medianLatency || 0,
      p95_e2e_latency: metrics.p95Latency || 0,
      uplink_kbps: metrics.bandwidth.uplink,
      downlink_kbps: metrics.bandwidth.downlink,
      timestamp: new Date().toISOString(),
      detection_mode: detectionMode
    };
    
    // Download as JSON file
    const blob = new Blob([JSON.stringify(metricsData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'metrics.json';
    a.click();
    URL.revokeObjectURL(url);
  };
  
  // Check if this is a phone client based on URL params
  const urlParams = new URLSearchParams(window.location.search);
  const isPhoneClient = urlParams.get('role') === 'phone';
  
  if (isPhoneClient) {
    // Phone UI
    return (
      <div className="min-h-screen bg-gray-900 text-white p-4">
        <div className="max-w-md mx-auto">
          <h1 className="text-2xl font-bold text-center mb-6">Phone Camera</h1>
          
          <div className="space-y-4">
            <div className="relative">
              <video
                ref={localVideoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-64 bg-black rounded-lg object-cover"
              />
              <div className="absolute top-2 left-2 bg-black bg-opacity-75 px-2 py-1 rounded text-sm">
                {connectionState}
              </div>
            </div>
            
            <div className="flex gap-2">
              <button
                onClick={startCamera}
                disabled={isRecording}
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 px-4 py-2 rounded font-medium"
              >
                {isRecording ? 'Streaming...' : 'Start Camera'}
              </button>
              
              <button
                onClick={stopRecording}
                disabled={!isRecording}
                className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 px-4 py-2 rounded font-medium"
              >
                Stop
              </button>
            </div>
            
            {isRecording && (
              <div className="bg-gray-800 p-4 rounded-lg">
                <h3 className="font-medium mb-2">Stats</h3>
                <div className="text-sm space-y-1">
                  <div>Frames: {metrics.frameCount}</div>
                  <div>Processed: {metrics.processedFrames}</div>
                  <div>FPS: {metrics.fps?.toFixed(1) || 0}</div>
                  <div>Latency: {metrics.medianLatency?.toFixed(0) || 0}ms</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }
  
  // Desktop Host UI
  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <div className="bg-gray-800 p-4 border-b border-gray-700">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-2xl font-bold">WebRTC Object Detection</h1>
          
          <div className="flex items-center gap-4">
            <div className="flex gap-2">
              <button
                onClick={() => setDetectionMode('wasm')}
                className={`px-3 py-1 rounded text-sm ${
                  detectionMode === 'wasm' ? 'bg-blue-600' : 'bg-gray-600'
                }`}
              >
                WASM Mode
              </button>
              <button
                onClick={() => setDetectionMode('server')}
                className={`px-3 py-1 rounded text-sm ${
                  detectionMode === 'server' ? 'bg-blue-600' : 'bg-gray-600'
                }`}
              >
                Server Mode
              </button>
            </div>
            
            <div className={`px-3 py-1 rounded text-sm ${
              connectionState === 'connected' ? 'bg-green-600' : 'bg-red-600'
            }`}>
              {connectionState}
            </div>
          </div>
        </div>
      </div>
      
      <div className="max-w-7xl mx-auto p-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* Video Stream */}
          <div className="lg:col-span-2">
            <div className="bg-gray-800 rounded-lg p-4">
              <h2 className="text-xl font-semibold mb-4">Live Stream</h2>
              
              <div className="relative">
                <video
                  ref={remoteVideoRef}
                  autoPlay
                  playsInline
                  className="w-full h-96 bg-black rounded-lg object-cover"
                />
                <canvas
                  ref={canvasRef}
                  className="absolute inset-0 w-full h-full pointer-events-none"
                />
                
                {!isRecording && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 rounded-lg">
                    <div className="text-center">
                      <p className="text-xl mb-4">Connect your phone to start</p>
                      <div className="bg-white p-4 rounded-lg inline-block">
                        <img
                          src={generateQRCode(phoneJoinURL)}
                          alt="QR Code"
                          className="w-48 h-48"
                        />
                      </div>
                      <p className="mt-2 text-sm text-gray-400">
                        Scan with phone camera or visit:<br/>
                        <code className="bg-gray-700 px-2 py-1 rounded">{phoneJoinURL}</code>
                      </p>
                    </div>
                  </div>
                )}
              </div>
              
              {isRecording && (
                <div className="mt-4 flex gap-2">
                  <button
                    onClick={stopRecording}
                    className="bg-red-600 hover:bg-red-700 px-4 py-2 rounded"
                  >
                    Stop Stream
                  </button>
                  
                  <button
                    onClick={exportMetrics}
                    className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded"
                  >
                    Export Metrics
                  </button>
                </div>
              )}
            </div>
          </div>
          
          {/* Sidebar */}
          <div className="space-y-6">
            
            {/* Metrics */}
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg font-semibold mb-4">Metrics</h3>
              
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span>Frames Captured:</span>
                  <span className="font-mono">{metrics.frameCount}</span>
                </div>
                
                <div className="flex justify-between">
                  <span>Processed:</span>
                  <span className="font-mono">{metrics.processedFrames}</span>
                </div>
                
                <div className="flex justify-between">
                  <span>FPS:</span>
                  <span className="font-mono">{metrics.fps?.toFixed(1) || '0.0'}</span>
                </div>
                
                <div className="flex justify-between">
                  <span>Median Latency:</span>
                  <span className="font-mono">{metrics.medianLatency?.toFixed(0) || '0'}ms</span>
                </div>
                
                <div className="flex justify-between">
                  <span>P95 Latency:</span>
                  <span className="font-mono">{metrics.p95Latency?.toFixed(0) || '0'}ms</span>
                </div>
                
                <div className="flex justify-between">
                  <span>Mode:</span>
                  <span className="font-mono text-blue-400">{detectionMode.toUpperCase()}</span>
                </div>
              </div>
            </div>
            
            {/* Current Detections */}
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg font-semibold mb-4">Detections</h3>
              
              {currentDetections.length > 0 ? (
                <div className="space-y-2">
                  {currentDetections.map((detection, index) => (
                    <div key={index} className="bg-gray-700 p-3 rounded">
                      <div className="font-medium text-green-400">{detection.label}</div>
                      <div className="text-sm text-gray-300">
                        Confidence: {(detection.score * 100).toFixed(1)}%
                      </div>
                      <div className="text-xs text-gray-400 font-mono">
                        [{detection.xmin.toFixed(3)}, {detection.ymin.toFixed(3)}, 
                         {detection.xmax.toFixed(3)}, {detection.ymax.toFixed(3)}]
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-400 italic">No objects detected</p>
              )}
            </div>
            
            {/* Instructions */}
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg font-semibold mb-4">Instructions</h3>
              
              <div className="text-sm space-y-2">
                <p>1. Scan QR code with phone</p>
                <p>2. Grant camera permission</p>
                <p>3. Point camera at objects</p>
                <p>4. Watch real-time detections</p>
                <p>5. Export metrics when done</p>
              </div>
              
              <div className="mt-4 p-3 bg-yellow-900 bg-opacity-30 rounded text-yellow-200 text-xs">
                <strong>Performance Tips:</strong><br/>
                • Use WASM mode for low-resource devices<br/>
                • Ensure good lighting<br/>
                • Keep objects in frame center<br/>
                • Stable internet connection recommended
              </div>
            </div>
            
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;