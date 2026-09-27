import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  WASocket,
  fetchLatestBaileysVersion,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import QRCode from 'qrcode';
import pino from 'pino';
import fs from 'fs';
import path from 'path';

export type ConnectionState = 'connecting' | 'qr_ready' | 'connected' | 'disconnected';

export interface WhatsAppStatus {
  status: ConnectionState;
  phone: string | null;
  qrCodeDataUrl: string | null;
  lastConnected: string | null;
}

export class WhatsAppManager {
  private sock: WASocket | null = null;
  private authDir: string;
  private status: ConnectionState = 'disconnected';
  private qrCodeDataUrl: string | null = null;
  private connectedPhone: string | null = null;
  private lastConnected: string | null = null;
  private logger = pino({ level: 'warn' });
  private isInitializing = false;

  constructor(authDir?: string) {
    this.authDir = authDir || process.env.WHATSAPP_AUTH_DIR || path.join(process.cwd(), 'data', 'whatsapp_auth');
    if (!fs.existsSync(this.authDir)) {
      fs.mkdirSync(this.authDir, { recursive: true });
    }
  }

  public getStatus(): WhatsAppStatus {
    return {
      status: this.status,
      phone: this.connectedPhone,
      qrCodeDataUrl: this.qrCodeDataUrl,
      lastConnected: this.lastConnected,
    };
  }

  public async init(): Promise<void> {
    if (this.isInitializing) return;
    this.isInitializing = true;
    this.status = 'connecting';

    try {
      const { state, saveCreds } = await useMultiFileAuthState(this.authDir);
      const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: [2, 3000, 1015901307] as any }));

      this.sock = makeWASocket({
        version,
        auth: state,
        logger: this.logger,
        printQRInTerminal: false,
        browser: ['Authentik Access Manager', 'Chrome', '1.0.0'],
        connectTimeoutMs: 60000,
        keepAliveIntervalMs: 25000,
      });

      this.sock.ev.on('creds.update', saveCreds);

      this.sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
          try {
            this.qrCodeDataUrl = await QRCode.toDataURL(qr, {
              margin: 2,
              scale: 6,
              color: {
                dark: '#0f172a',
                light: '#ffffff',
              },
            });
            this.status = 'qr_ready';
          } catch (err) {
            console.error('Failed to generate QR data URL:', err);
          }
        }

        if (connection === 'open') {
          this.status = 'connected';
          this.qrCodeDataUrl = null;
          this.lastConnected = new Date().toISOString();
          const userJid = this.sock?.user?.id || '';
          this.connectedPhone = userJid.split(':')[0] || userJid.split('@')[0] || 'Unknown';
          console.log(`[WhatsApp] Connected successfully as +${this.connectedPhone}`);
        } else if (connection === 'close') {
          const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
          const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

          console.log(`[WhatsApp] Connection closed (code: ${statusCode}). Reconnect: ${shouldReconnect}`);

          this.status = 'disconnected';
          this.connectedPhone = null;

          if (shouldReconnect) {
            setTimeout(() => {
              this.isInitializing = false;
              this.init();
            }, 3000);
          } else {
            console.log('[WhatsApp] Logged out by server. Resetting session...');
            await this.clearAuthFiles();
            setTimeout(() => {
              this.isInitializing = false;
              this.init();
            }, 1000);
          }
        }
      });
    } catch (err) {
      console.error('[WhatsApp] Initialization error:', err);
      this.status = 'disconnected';
    } finally {
      this.isInitializing = false;
    }
  }

  public async sendMessage(rawRecipient: string, message: string): Promise<{ success: boolean; messageId?: string }> {
    if (this.status !== 'connected' || !this.sock) {
      throw new Error('WhatsApp is not connected. Please scan the QR code to pair your device.');
    }

    const jid = this.formatRecipientJid(rawRecipient);

    try {
      const sent = await this.sock.sendMessage(jid, { text: message });
      return {
        success: true,
        messageId: sent?.key?.id || undefined,
      };
    } catch (err: any) {
      console.error(`[WhatsApp] Failed to send message to ${jid}:`, err);
      throw new Error(`Failed to send WhatsApp message: ${err.message || err}`);
    }
  }

  public async logout(): Promise<void> {
    try {
      if (this.sock) {
        await this.sock.logout().catch(() => {});
        this.sock.end(undefined);
      }
    } catch (err) {
      console.error('[WhatsApp] Error during logout:', err);
    } finally {
      await this.clearAuthFiles();
      this.status = 'disconnected';
      this.connectedPhone = null;
      this.qrCodeDataUrl = null;
      this.isInitializing = false;
      // Re-initialize to offer fresh QR code
      setTimeout(() => this.init(), 1000);
    }
  }

  private async clearAuthFiles(): Promise<void> {
    try {
      if (fs.existsSync(this.authDir)) {
        fs.rmSync(this.authDir, { recursive: true, force: true });
        fs.mkdirSync(this.authDir, { recursive: true });
      }
    } catch (err) {
      console.error('[WhatsApp] Error clearing auth files:', err);
    }
  }

  private formatRecipientJid(recipient: string): string {
    // Strip non-numeric characters except leading +
    let cleaned = recipient.replace(/[^\d+]/g, '');

    // Remove leading +
    if (cleaned.startsWith('+')) {
      cleaned = cleaned.substring(1);
    }

    // Handle local numbers starting with 0 if default country code is provided
    const defaultCountryCode = process.env.DEFAULT_COUNTRY_CODE || '44'; // Default UK or configurable
    if (cleaned.startsWith('0')) {
      cleaned = defaultCountryCode + cleaned.substring(1);
    }

    if (cleaned.length < 7) {
      throw new Error(`Invalid phone number: ${recipient}`);
    }

    return `${cleaned}@s.whatsapp.net`;
  }
}

export const whatsappManager = new WhatsAppManager();
