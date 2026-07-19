const WebSocket = require('ws');
const ws = new WebSocket('ws://127.0.0.1:8000/ws');

ws.on('open', () => {
  console.log('Connected');
  process.exit(0);
});

ws.on('error', (err) => {
  console.log('Error:', err.message);
  process.exit(1);
});

ws.on('unexpected-response', (req, res) => {
  console.log('Unexpected response:', res.statusCode);
  console.log('Headers:', JSON.stringify(res.headers, null, 2));
  process.exit(1);
});
