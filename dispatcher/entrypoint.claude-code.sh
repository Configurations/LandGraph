#!/usr/bin/env bash
set -euo pipefail

# ── Read Task from stdin ────────────────────────────
TASK_JSON=$(cat /dev/stdin)
TASK_ID=$(echo "$TASK_JSON" | jq -r '.task_id')
INSTRUCTION=$(echo "$TASK_JSON" | jq -r '.payload.instruction')
TIMEOUT=$(echo "$TASK_JSON" | jq -r '.timeout_seconds // 300')

# ── Build context with previous answers if resuming ─
PREV_ANSWERS=$(echo "$TASK_JSON" | jq -r '.payload.previous_answers // [] | length')
if [ "$PREV_ANSWERS" -gt 0 ]; then
    CONTEXT_PREFIX="[REPRISE] Reponses precedentes :\n"
    CONTEXT_PREFIX+=$(echo "$TASK_JSON" | jq -r '.payload.previous_answers[] | "Q: \(.question)\nR: \(.answer)\n"')
    INSTRUCTION="$CONTEXT_PREFIX\n---\n$INSTRUCTION"
fi

# ── Helper: emit a protocol event ───────────────────
emit_event() {
    local type=$1
    local data=$2
    echo "{\"task_id\":\"$TASK_ID\",\"type\":\"$type\",\"data\":$data}"
}

emit_event "progress" "\"Agent $AGENT_ROLE demarre - tache $TASK_ID\""

# ── Run Claude Code ─────────────────────────────────
EXIT_CODE=0
RESULT=$(timeout "$TIMEOUT" claude \
    -p "$INSTRUCTION" \
    --output-format stream-json \
    --allowedTools "$AGENT_ALLOWED_TOOLS" \
    --max-turns "$AGENT_MAX_TURNS" \
    2>/dev/null) || EXIT_CODE=$?

# ── Parse Claude Code stream events ─────────────────
echo "$RESULT" | while IFS= read -r line; do
    TYPE=$(echo "$line" | jq -r '.type // empty' 2>/dev/null) || continue
    case "$TYPE" in
        "assistant")
            TEXT=$(echo "$line" | jq -c '.message.content[]? | select(.type=="text") | .text' 2>/dev/null)
            [ -n "$TEXT" ] && emit_event "progress" "$TEXT"
            ;;
        "tool_use")
            TOOL_NAME=$(echo "$line" | jq -r '.name // empty' 2>/dev/null)
            case "$TOOL_NAME" in
                Write|Edit)
                    ARTIFACT=$(echo "$line" | jq -c '{key: .input.file_path, content: (.input.content // .input.new_string // ""), deliverable_type: "delivers_code"}' 2>/dev/null)
                    emit_event "artifact" "$ARTIFACT"
                    ;;
                *)
                    TOOL_INFO=$(echo "$line" | jq -c '{tool: .name, input: .input}' 2>/dev/null)
                    emit_event "progress" "$TOOL_INFO"
                    ;;
            esac
            ;;
        "result")
            COST=$(echo "$line" | jq -r '.cost_usd // 0' 2>/dev/null)
            emit_event "progress" "\"cost_usd: $COST\""
            ;;
    esac
done

# ── Emit terminal event ─────────────────────────────
if [ "$EXIT_CODE" -eq 0 ]; then
    emit_event "result" "{\"status\":\"success\",\"exit_code\":0}"
else
    emit_event "result" "{\"status\":\"failure\",\"exit_code\":$EXIT_CODE}"
fi

exit $EXIT_CODE
