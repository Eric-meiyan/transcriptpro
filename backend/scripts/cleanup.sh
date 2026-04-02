#!/bin/bash
# Clean up temp audio files older than 2 hours
# Add to crontab: 0 * * * * /opt/transcriptpro/backend/scripts/cleanup.sh

find /root/.transcriptpro/temp -type f -mmin +120 -delete 2>/dev/null
echo "$(date): Cleanup done"
