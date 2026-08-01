#!/usr/bin/env bash  
test_hister() { curl --max-time 15 http://host.docker.internal:4433/health >/dev/null && echo "[✓] Hister API responding"; }  

echo "[$(date +%H:%M)] Testing..." ; test_hister | tail -1; exit 0 || true  
