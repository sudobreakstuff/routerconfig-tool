#!/bin/sh
if [ -f /opt/RouterConfigPro/chrome-sandbox ]; then
  chown root:root /opt/RouterConfigPro/chrome-sandbox 2>/dev/null || true
  chmod 4755 /opt/RouterConfigPro/chrome-sandbox 2>/dev/null || true
fi
exit 0
