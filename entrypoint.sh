#!/bin/sh
set -e

# Ensure data directory and WhatsApp authentication directory exist
mkdir -p /app/data/whatsapp_auth

# Execute supervisord as the main container process
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
