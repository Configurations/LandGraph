#!/usr/bin/env bash
set -euo pipefail

# Read Task JSON from stdin
TASK_JSON=$(cat /dev/stdin)
TASK_ID=$(echo "$TASK_JSON" | jq -r '.task_id')
INSTRUCTION=$(echo "$TASK_JSON" | jq -r '.payload.instruction')

emit_event() {
    local type=$1
    local data=$2
    echo "{\"task_id\":\"$TASK_ID\",\"type\":\"$type\",\"data\":$data}"
}

# 1. Progress: started
emit_event "progress" "\"Test agent started - task $TASK_ID\""

# 2. Artifact: first deliverable
sleep 1
emit_event "artifact" "{\"key\":\"test-deliverable\",\"content\":\"# Test Deliverable\\n\\nProduced by test agent.\\n\\nInstruction: $INSTRUCTION\",\"deliverable_type\":\"delivers_docs\"}"

# 3. Question: ask human
sleep 1
emit_event "question" "{\"prompt\":\"Approche A ou approche B ?\",\"context\":{\"options\":[\"A\",\"B\"]}}"

# 4. Wait for answer on stdin
read -r ANSWER_JSON
ANSWER=$(echo "$ANSWER_JSON" | jq -r '.response // "no response"')
emit_event "progress" "\"Received answer: $ANSWER\""

# 5. Second artifact based on answer
sleep 1
emit_event "artifact" "{\"key\":\"final-report\",\"content\":\"# Final Report\\n\\nAnswer received: $ANSWER\\n\\nTest completed.\",\"deliverable_type\":\"delivers_docs\"}"

# 6. Result: success
emit_event "result" "{\"status\":\"success\",\"exit_code\":0,\"cost_usd\":0.001}"

exit 0
