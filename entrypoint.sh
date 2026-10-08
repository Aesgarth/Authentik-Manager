#!/bin/sh
set -e

# Ensure data directory and WhatsApp authentication directory exist with proper permissions
mkdir -p /app/data/whatsapp_auth
chown -R appuser:appuser /app/data

# Execute supervisord as the main container process
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
