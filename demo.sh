#!/usr/bin/env bash
# ==============================================================================
# GPUShip — Decisive Demo CLI Runner (§8.5)
# "Git push -> build -> live API -> idle -> GPU released -> new job -> replacement GPU -> completed response using the same URL"
# ==============================================================================
set -e

BASE_URL="http://localhost:8000"

# Colors for terminal presentation
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "\n${BOLD}${CYAN}================================================================${NC}"
echo -e "${BOLD}${CYAN}   GPUShip — Decisive Scale-to-Zero Verification Demo${NC}"
echo -e "${CYAN}   Compute Backend: Lium Cloud | Scale Target: \\\$0.00/hr Idle${NC}"
echo -e "${BOLD}${CYAN}================================================================${NC}\n"

# 1. Check if GPUShip is running
echo -e "${BLUE}[1/6] Checking GPUShip CPU Gateway health...${NC}"
HEALTH=$(curl -s "${BASE_URL}/health" || echo "")
if [[ -z "$HEALTH" ]]; then
  echo -e "${YELLOW}GPUShip server not detected on ${BASE_URL}.${NC}"
  echo -e "Starting GPUShip local server in background..."
  python3 -m gpuship.main > /tmp/gpuship.log 2>&1 &
  SERVER_PID=$!
  sleep 2
  echo -e "${GREEN}✓ GPUShip CPU Gateway running (PID ${SERVER_PID})${NC}"
else
  echo -e "${GREEN}✓ GPUShip CPU Gateway online${NC}"
fi

# 2. Trigger the decisive demo pipeline via API
echo -e "\n${BLUE}[2/6] Triggering Decisive Demo sequence via API...${NC}"
DEMO_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/demo/run-decisive")

STATUS=$(echo "$DEMO_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'ERROR'))" 2>/dev/null || echo "ERROR")

if [[ "$STATUS" != "DECISIVE_DEMO_PASSED" ]]; then
  echo -e "${RED}✗ Demo run failed:${NC}"
  echo "$DEMO_RESPONSE"
  exit 1
fi

echo -e "\n${GREEN}${BOLD}✓ DECISIVE DEMO COMPLETED SUCCESSFULLY!${NC}\n"

# 3. Print parsed trace steps
echo -e "${BOLD}Execution Trace Breakdown:${NC}"
python3 - <<EOF
import json, sys

data = json.loads('''$DEMO_RESPONSE''')
trace = data.get('trace', [])
summary = data.get('summary', {})

for step in trace:
    s_name = step.get('step')
    s_status = step.get('status')
    details = step.get('details', {})
    
    if s_name == "1_GIT_PUSH_AND_BUILD" and s_status == "COMPLETED":
        print(f"  \033[1;32m✓ Step 1: Git Push & Container Build\033[0m")
        print(f"    - Deployment ID: {details.get('deployment_id')}")
        print(f"    - Image Tag: {details.get('image_tag')}")
    elif s_name == "2_LIVE_API_REQUEST" and s_status == "COMPLETED":
        print(f"  \033[1;32m✓ Step 2: First Job on Stable URL (Cold Start)\033[0m")
        print(f"    - Job ID: {details.get('job_id')}")
        print(f"    - Execution Latency: {details.get('latency_ms', 0):.1f}ms")
    elif s_name == "3_IDLE_SCALE_TO_ZERO" and s_status == "POD_RELEASED":
        print(f"  \033[1;32m✓ Step 3: Idle Timer Expired -> Scaled to Zero\033[0m")
        print(f"    - Active GPUs: {details.get('active_gpu_count')}")
        print(f"    - Compute Spend: {details.get('compute_cost_per_hour')}")
    elif s_name == "4_NEW_REQUEST_SAME_URL" and s_status == "COMPLETED":
        print(f"  \033[1;32m✓ Step 4: Second Job on IDENTICAL Stable URL (Replacement GPU)\033[0m")
        print(f"    - Job ID: {details.get('job_id')}")
        print(f"    - Execution Latency: {details.get('latency_ms', 0):.1f}ms")

print("\n\033[1mEconomic Summary:\033[0m")
print(f"  - Cost Savings vs Always-On: \033[1;32m{summary.get('savings_vs_always_on')}\033[0m")
print(f"  - Stable Endpoint: \033[36m{data.get('stable_url')}\033[0m")
print(f"  - Verified Outcome: \033[1;32m{summary.get('demo_outcome')}\033[0m")
EOF

echo -e "\n${BOLD}${CYAN}================================================================${NC}"
echo -e "${BOLD}${CYAN}   Interactive Dashboard: http://localhost:8000${NC}"
echo -e "${BOLD}${CYAN}================================================================${NC}\n"
