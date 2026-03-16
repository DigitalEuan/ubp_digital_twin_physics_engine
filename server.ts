import express from 'express';
import { createServer as createViteServer } from 'vite';
import { WebSocketServer, WebSocket } from 'ws';
import { spawn } from 'child_process';
import path from 'path';

async function startServer() {
  const app = express();
  const PORT = 3000;

  // API routes
  app.get('/api/health', (req, res) => {
    res.json({ status: 'ok' });
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const server = app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });

  // WebSocket Server
  const wss = new WebSocketServer({ server, path: '/ws' });
  
  // Start Python Bridge
  const pythonProcess = spawn('python3', ['python_bridge.py']);
  
  let lastState = '';
  let stdoutBuffer = '';

  pythonProcess.stdout.on('data', (data) => {
    stdoutBuffer += data.toString();
    const lines = stdoutBuffer.split('\n');
    
    // Keep the last incomplete line in the buffer
    stdoutBuffer = lines.pop() || '';

    for (const line of lines) {
      if (line.trim()) {
        lastState = line;
        // Broadcast state to all connected clients
        wss.clients.forEach((client) => {
          if (client.readyState === WebSocket.OPEN) {
            client.send(line);
          }
        });
      }
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`Python Error: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
  });

  wss.on('connection', (ws) => {
    console.log('Client connected');
    
    // Send last known state immediately
    if (lastState) {
      ws.send(lastState);
    }

    ws.on('message', (message) => {
      // Forward commands to Python bridge
      pythonProcess.stdin.write(message.toString() + '\n');
    });

    ws.on('close', () => {
      console.log('Client disconnected');
    });
  });
}

startServer();
