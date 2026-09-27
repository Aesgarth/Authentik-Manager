import express, { Request, Response } from 'express';
import cors from 'cors';
import { whatsappManager } from './whatsapp.js';

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// Health check
app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok', service: 'whatsapp-baileys-bridge' });
});

// Connection status & QR code
app.get('/status', (_req: Request, res: Response) => {
  res.json(whatsappManager.getStatus());
});

// Send message
app.post('/send', async (req: Request, res: Response) => {
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
app.post('/logout', async (_req: Request, res: Response) => {
  try {
    await whatsappManager.logout();
    res.json({ status: 'logged_out', message: 'WhatsApp session cleared. Scan new QR code.' });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`[WhatsApp Service] Baileys bridge listening on port ${PORT}`);
  // Initialize connection
  whatsappManager.init().catch((err) => {
    console.error('[WhatsApp Service] Startup init error:', err);
  });
});
