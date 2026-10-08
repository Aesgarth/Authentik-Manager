import express, { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';
import { whatsappManager } from './whatsapp.js';
import { getBridgeSecret } from './secret.js';

const app = express();
const PORT = Number(process.env.PORT) || 3001;
const INTERNAL_SECRET = getBridgeSecret();

app.use(express.json());

// Verify shared secret for internal bridge communication
const verifyInternalAuth = (req: Request, res: Response, next: NextFunction) => {
  if (!INTERNAL_SECRET) {
    const clientIp = req.socket.remoteAddress || '';
    if (clientIp === '127.0.0.1' || clientIp === '::1' || clientIp === '::ffff:127.0.0.1') {
      return next();
    }
    return res.status(401).json({ error: 'Unauthorized internal request' });
  }

  const provided = (req.headers['x-bridge-secret'] || req.headers['x-internal-token'] || '') as string;
  try {
    const bufProvided = Buffer.from(provided);
    const bufExpected = Buffer.from(INTERNAL_SECRET);
    if (bufProvided.length !== bufExpected.length || !crypto.timingSafeEqual(bufProvided, bufExpected)) {
      return res.status(401).json({ error: 'Unauthorized internal request' });
    }
  } catch {
    return res.status(401).json({ error: 'Unauthorized internal request' });
  }
  next();
};

// Health check
app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok', service: 'whatsapp-baileys-bridge' });
});

// Connection status & QR code
app.get('/status', verifyInternalAuth, (_req: Request, res: Response) => {
  res.json(whatsappManager.getStatus());
});

// Send message
app.post('/send', verifyInternalAuth, async (req: Request, res: Response) => {
  const { recipient, message } = req.body;

  if (!recipient || !message) {
    return res.status(400).json({ error: 'recipient and message are required' });
  }

  try {
    const result = await whatsappManager.sendMessage(recipient, message);
    return res.json(result);
  } catch (err: any) {
    console.error('Error sending WhatsApp message:', err.message);
    return res.status(500).json({ error: err.message || 'Failed to send message' });
  }
});

// Logout / Disconnect device
app.post('/logout', verifyInternalAuth, async (_req: Request, res: Response) => {
  try {
    await whatsappManager.logout();
    res.json({ status: 'logged_out', message: 'WhatsApp session cleared. Scan new QR code.' });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// Bind exclusively to 127.0.0.1 loopback
app.listen(PORT, '127.0.0.1', () => {
  console.log(`[WhatsApp Service] Baileys bridge listening on 127.0.0.1:${PORT}`);
  // Initialize connection
  whatsappManager.init().catch((err) => {
    console.error('[WhatsApp Service] Startup init error:', err);
  });
});
