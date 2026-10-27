#!/usr/bin/env bash
# ==============================================================================
# GPUShip — One-Click Platform Launcher
# Starts the Stable CPU Gateway, Reconciler Engine, and Dashboard
# ==============================================================================
set -e

PORT=8000
HOST="0.0.0.0"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "\n${BOLD}${CYAN}================================================================${NC}"
echo -e "${BOLD}${CYAN}   GPUShip — Scale-to-Zero GPU Deployment Platform for Lium${NC}"
echo -e "${BOLD}${CYAN}================================================================${NC}\n"
echo -e "${GREEN}Starting GPUShip on http://${HOST}:${PORT}${NC}"
echo -e "Dashboard:      ${CYAN}http://localhost:${PORT}${NC}"
echo -e "API Gateway:    ${CYAN}http://localhost:${PORT}/api/v1${NC}"
echo -e "Health Check:   ${CYAN}http://localhost:${PORT}/health${NC}\n"

exec python3 -m gpuship.main

