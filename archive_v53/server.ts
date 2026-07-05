/**
 * UBP Digital Twin — Unified Server
 *
 * Architecture:
 *   Browser <—— WebSocket /ws ——> ws.WebSocketServer (port 3000)
 *                                        |
 *                                  stdin / stdout
 *                                        |
 *                               python_bridge.py
 *
 * Single port only. No proxy. No second Python HTTP server.
 */

import express from 'express';
import { createServer } from 'http';
import { createServer as createViteServer } from 'vite';
import { spawn, ChildProcess } from 'child_process';
import { WebSocketServer, WebSocket } from 'ws';
import path from 'path';
import readline from 'readline';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface BridgeMessage {
  type: string;
  req_id?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Python bridge — stdin/stdout pipe to python_bridge.py
// ---------------------------------------------------------------------------
class PythonBridge {
  private proc: ChildProcess | null = null;
  public logs: string[] = [];

  // Pending HTTP request/response promises keyed by req_id
  private pending = new Map<string, (msg: BridgeMessage) => void>();

  constructor(private onBroadcast: (msg: BridgeMessage) => void) {}

  private log(line: string) {
    this.logs.push(line);
    if (this.logs.length > 500) this.logs.splice(0, 200);
  }

  start() {
    console.log('[Bridge] Spawning python_bridge.py...');
    this.proc = spawn('python3', ['python_bridge.py'], {
      cwd: process.cwd(),
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });

    this.proc.on('error', (err) => {
      console.error('[Bridge] Spawn error:', err.message);
      this.log('SPAWN ERROR: ' + err.message);
    });

    // stdout = newline-delimited JSON
    readline.createInterface({ input: this.proc.stdout! }).on('line', (line) => {
      if (!line.trim()) return;
      try {
        const msg: BridgeMessage = JSON.parse(line);
        // Check if this is a response to a pending HTTP request
        if (msg.req_id && this.pending.has(msg.req_id)) {
          const resolve = this.pending.get(msg.req_id)!;
          this.pending.delete(msg.req_id);
          resolve(msg);
        } else {
          // Regular broadcast message (state, synthesis_event, etc.)
          this.onBroadcast(msg);
        }
      } catch {
        console.log('[Python]', line);
        this.log(line);
      }
    });

    // stderr = Python logging + tracebacks
    readline.createInterface({ input: this.proc.stderr! }).on('line', (line) => {
      console.error('[Python]', line);
      this.log('ERR: ' + line);
    });

    this.proc.on('exit', (code) => {
      console.error(`[Bridge] Python exited (code ${code}). See /python-status.`);
      this.log(`EXIT code=${code}`);
      // Reject all pending requests
      for (const [id, resolve] of this.pending) {
        resolve({ type: 'error', req_id: id, error: `Python exited with code ${code}` });
      }
      this.pending.clear();
    });

    console.log(`[Bridge] Python pid=${this.proc.pid}`);
  }

  /** Send a fire-and-forget message to Python. */
  send(msg: object) {
    if (this.proc?.stdin?.writable) {
      this.proc.stdin.write(JSON.stringify(msg) + '\n');
    }
  }

  /**
   * Send a message to Python and wait for a matching response by req_id.
   * Times out after `timeoutMs` milliseconds.
   */
  request(msg: BridgeMessage, timeoutMs = 8000): Promise<BridgeMessage> {
    return new Promise((resolve) => {
      const req_id = msg.req_id ?? `req_${Date.now()}_${Math.random()}`;
      const msgWithId = { ...msg, req_id };

      const timer = setTimeout(() => {
        if (this.pending.has(req_id)) {
          this.pending.delete(req_id);
          resolve({ type: 'error', req_id, error: 'Request timed out' });
        }
      }, timeoutMs);

      this.pending.set(req_id, (response) => {
        clearTimeout(timer);
        resolve(response);
      });

      this.send(msgWithId);
    });
  }

  get pid()     { return this.proc?.pid ?? null; }
  get running() { return !!this.proc && this.proc.exitCode === null && !this.proc.killed; }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function startServer() {
  const PORT = parseInt(process.env.PORT ?? '3000', 10);

  const app = express();
  const httpServer = createServer(app);

  const clients = new Set<WebSocket>();
  let lastState: BridgeMessage | null = null;

  const broadcast = (data: string) => {
    for (const ws of clients) {
      if (ws.readyState === WebSocket.OPEN) {
        try { ws.send(data); } catch { /* ignore */ }
      }
    }
  };

  // Start Python bridge
  const bridge = new PythonBridge((msg) => {
    // Cache latest state for the /last-state diagnostic
    if (msg.type === 'state') lastState = msg;
    broadcast(JSON.stringify(msg));
  });
  bridge.start();

  // WebSocket server
  const wss = new WebSocketServer({ noServer: true });

  wss.on('connection', (ws) => {
    clients.add(ws);
    console.log(`[WS] Client connected (${clients.size} total)`);
    ws.on('message', (raw) => {
      try { bridge.send(JSON.parse(raw.toString())); }
      catch { /* ignore non-JSON */ }
    });
    ws.on('close', () => {
      clients.delete(ws);
      console.log(`[WS] Client disconnected (${clients.size} total)`);
    });
    ws.on('error', (e) => console.error('[WS] Error:', e.message));
  });

  // Route HTTP upgrades: /ws → WSS; everything else → destroy
  // (HMR is disabled in AI Studio via DISABLE_HMR=true)
  httpServer.on('upgrade', (req, socket, head) => {
    if ((req.url ?? '').startsWith('/ws')) {
      wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
    } else {
      socket.destroy();
    }
  });

  // -------------------------------------------------------------------------
  // HTTP endpoints
  // -------------------------------------------------------------------------

  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', clients: clients.size, python: bridge.running });
  });

  // Full Python stdout/stderr log — essential for diagnosing startup failures
  app.get('/python-status', (_req, res) => {
    res.json({ pid: bridge.pid, running: bridge.running, recent_logs: bridge.logs.slice(-80) });
  });

  // Last simulation state received from Python — diagnose serialisation issues
  app.get('/last-state', (_req, res) => {
    if (lastState) {
      res.json({ received: true, tick: (lastState as any)?.data?.tick ?? null, keys: Object.keys((lastState as any)?.data ?? {}) });
    } else {
      res.json({ received: false, message: 'No state received yet — check /python-status for errors' });
    }
  });

  // Engine test — send command to Python, await response, return as JSON
  app.get('/engine_test', async (_req, res) => {
    try {
      const result = await bridge.request({ type: 'command', command: 'engine_test' });
      if (result.error) {
        res.status(500).json({ pass: false, error: result.error });
      } else {
        res.json(result);
      }
    } catch (err) {
      res.status(500).json({ pass: false, error: String(err) });
    }
  });

  // -------------------------------------------------------------------------
  // Vite dev middleware — no httpServer passed, no HMR wiring
  // -------------------------------------------------------------------------
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const dist = path.join(process.cwd(), 'dist');
    app.use(express.static(dist));
    app.get('*', (_req, res) => res.sendFile(path.join(dist, 'index.html')));
  }

  // -------------------------------------------------------------------------
  // Listen
  // -------------------------------------------------------------------------
  httpServer.listen(PORT, '0.0.0.0', () => {
    console.log(`[Server] http://localhost:${PORT}`);
    console.log(`[Server] /python-status — Python logs`);
    console.log(`[Server] /last-state    — last sim state received`);
  });
}

startServer().catch((err) => {
  console.error('[Server] Fatal:', err);
  process.exit(1);
});