#!/bin/sh
set -e

# Ensure data directory and WhatsApp authentication directory exist with proper permissions
mkdir -p /app/data/whatsapp_auth

# Ensure persistent bridge secret exists and is accessible
if [ ! -f /app/data/.bridge_secret ]; then
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > /app/data/.bridge_secret
    chmod 600 /app/data/.bridge_secret
fi
export INTERNAL_SERVICE_SECRET="$(cat /app/data/.bridge_secret)"

chown -R appuser:appuser /app/data

# Execute supervisord as the main container process
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
