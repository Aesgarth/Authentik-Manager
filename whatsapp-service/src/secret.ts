import fs from 'fs';
import path from 'path';

export function getBridgeSecret(): string {
  if (process.env.INTERNAL_SERVICE_SECRET) {
    return process.env.INTERNAL_SERVICE_SECRET.trim();
  }
  const possiblePaths = [
    '/app/data/.bridge_secret',
    path.join(process.cwd(), 'data', '.bridge_secret'),
    path.join(process.cwd(), '..', 'data', '.bridge_secret'),
  ];
  for (const p of possiblePaths) {
    try {
      if (fs.existsSync(p)) {
        const val = fs.readFileSync(p, 'utf-8').trim();
        if (val) return val;
      }
    } catch {}
  }
  return '';
}
