import express from 'express';
import { createServer as createViteServer } from 'vite';
import { createServer as createHttpServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { spawn } from 'child_process';
import path from 'path';
import net from 'net';

// ---------------------------------------------------------------------------
// UBP Digital Twin — Development Server
// ---------------------------------------------------------------------------
// Architecture:
//   - Vite dev server for React/Three.js HMR (port 3000)
//   - FastAPI backend for physics simulation (port 8000)
//   - This server proxies /ws WebSocket connections to FastAPI
//   - HTTP /state and /command requests are proxied to FastAPI
// ---------------------------------------------------------------------------

const FASTAPI_PORT = 8000;
const DEV_PORT = 3000;

async function waitForFastAPI(port: number, maxWait = 10000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < maxWait) {
    await new Promise(resolve => setTimeout(resolve, 200));
    const ok = await new Promise<boolean>(resolve => {
      const sock = net.connect(port, '127.0.0.1');
      sock.on('connect', () => { sock.destroy(); resolve(true); });
      sock.on('error', () => { sock.destroy(); resolve(false); });
    });
    if (ok) return;
  }
  throw new Error(`FastAPI did not start on port ${port} within ${maxWait}ms`);
}

async function startServer() {
  const app = express();
  const PORT = DEV_PORT;

  // ---- Start FastAPI backend ----
  console.log('[UBP] Starting FastAPI backend on port 8000...');
  const fastapi = spawn('python3', ['-m', 'uvicorn', 'ubp_server_v3:app', '--host', '0.0.0.0', '--port', '8000', '--log-level', 'warning'], {
    cwd: path.join(process.cwd()),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  fastapi.stdout.on('data', (d: Buffer) => process.stdout.write(`[FastAPI] ${d}`));
  fastapi.stderr.on('data', (d: Buffer) => process.stderr.write(`[FastAPI] ${d}`));
  fastapi.on('close', (code: number) => console.log(`[FastAPI] exited with code ${code}`));

  // Wait for FastAPI to be ready
  try {
    await waitForFastAPI(FASTAPI_PORT);
    console.log('[UBP] FastAPI backend ready');
  } catch (e) {
    console.error('[UBP] FastAPI failed to start:', e);
  }

  // ---- Vite dev server ----
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req: express.Request, res: express.Response) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const server = createHttpServer(app);
  const wss = new WebSocketServer({ server, path: '/ws' });

  // ---- Proxy /ws to FastAPI WebSocket ----
  wss.on('connection', (clientWs) => {
    console.log('[UBP] Client connected — proxying to FastAPI ws');

    const fastapiWs = new WebSocket(`ws://127.0.0.1:${FASTAPI_PORT}/ws`);
    let fastapiReady = false;
    const pending: string[] = [];

    fastapiWs.on('open', () => {
      fastapiReady = true;
      pending.forEach(msg => fastapiWs.send(msg));
      pending.length = 0;
    });

    fastapiWs.on('message', (data) => {
      if (clientWs.readyState === WebSocket.OPEN) {
        clientWs.send(data.toString());
      }
    });

    fastapiWs.on('close', () => {
      if (clientWs.readyState === WebSocket.OPEN) clientWs.close();
    });

    fastapiWs.on('error', (err) => {
      console.error('[UBP] FastAPI WS error:', err.message);
    });

    clientWs.on('message', (message) => {
      const msg = message.toString();
      if (fastapiReady) {
        fastapiWs.send(msg);
      } else {
        pending.push(msg);
      }
    });

    clientWs.on('close', () => {
      fastapiWs.close();
    });
  });

  server.listen(PORT, '0.0.0.0', () => {
    console.log(`[UBP] Dev server running on http://localhost:${PORT}`);
    console.log(`[UBP] Physics backend: http://localhost:${FASTAPI_PORT}`);
  });
}

startServer().catch(console.error);
