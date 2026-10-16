#!/usr/bin/env bash
# Self-refreshing launcher for a Claude Code worker session.
#
# Runs `claude` against a prompt file. If the run stops because the
# session/usage limit was hit, sleeps and relaunches with --continue so the
# SAME conversation picks back up, instead of the worker sitting idle in
# Terminal 2 until someone notices and restarts it by hand.
#
# IMPORTANT: `claude --continue` resumes the most recent conversation for
# the CURRENT WORKING DIRECTORY. Run this script from the same directory
# every time (default below: /home/user/nativeCamDev) even though the
# worker's own first step is to `cd` into a worktree - that `cd` happens
# INSIDE the conversation via tool calls, it does not change which
# conversation `--continue` reattaches to here.
#
# Best-effort: the exact wording Claude Code prints on a limit stop, and
# whether it exits the process or just idles in the TUI, was not observed
# in this environment before writing this script. The limit-phrase regex
# below is intentionally broad; if a real run exits non-zero WITHOUT one of
# these phrases, the script stops and hands control back rather than
# guessing.
#
# Usage:
#   ./claude_selfrefresh.sh <absolute-prompt-path> [model] [max_attempts]
set -uo pipefail

PROMPT_PATH="${1:?usage: $0 <absolute-prompt-path> [model] [max_attempts]}"
MODEL="${2:-sonnet}"
MAX_ATTEMPTS="${3:-30}"

if [[ ! -f "$PROMPT_PATH" ]]; then
    echo "[selfrefresh] no such prompt file: $PROMPT_PATH" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/selfrefresh-logs"
mkdir -p "$LOG_DIR"

DEFAULT_BACKOFF=1800   # 30 min fallback when no reset time can be parsed
LIMIT_RE='usage limit|rate limit|session limit|limit reached|resets at|try again (later|after)'

ATTEMPT=0
FIRST=1

while (( ATTEMPT < MAX_ATTEMPTS )); do
    ATTEMPT=$((ATTEMPT + 1))
    STAMP="$(date +%Y%m%d-%H%M%S)"
    LOG="$LOG_DIR/attempt-${ATTEMPT}-${STAMP}.log"

    if (( FIRST )); then
        echo "[selfrefresh] attempt $ATTEMPT/$MAX_ATTEMPTS: starting fresh run -> $LOG"
        claude --model "$MODEL" "run the prompt $PROMPT_PATH" 2>&1 | tee "$LOG"
        STATUS="${PIPESTATUS[0]}"
        FIRST=0
    else
        echo "[selfrefresh] attempt $ATTEMPT/$MAX_ATTEMPTS: resuming with --continue -> $LOG"
        claude --model "$MODEL" --continue \
            "the session limit reset - continue exactly where you left off on the restart-rebuild task, do not restart it" \
            2>&1 | tee "$LOG"
        STATUS="${PIPESTATUS[0]}"
    fi

    if [[ "$STATUS" -eq 0 ]]; then
        echo "[selfrefresh] claude exited 0 on attempt $ATTEMPT - treating as finished."
        echo "[selfrefresh] this only means the process exited clean, not that the deliverable landed - check the report, commits and analysis/28N file yourself."
        exit 0
    fi

    if grep -qiE "$LIMIT_RE" "$LOG"; then
        RESET_LINE="$(grep -iE 'reset' "$LOG" | tail -1)"
        echo "[selfrefresh] limit hit on attempt $ATTEMPT (exit $STATUS). ${RESET_LINE:-no reset time found in output}"
        echo "[selfrefresh] sleeping ${DEFAULT_BACKOFF}s before relaunch"
        sleep "$DEFAULT_BACKOFF"
        continue
    fi

    echo "[selfrefresh] claude exited $STATUS on attempt $ATTEMPT with no limit phrase in the log - stopping."
    echo "[selfrefresh] this looks like a real failure, not a usage limit. See $LOG"
    exit "$STATUS"
done

echo "[selfrefresh] hit MAX_ATTEMPTS ($MAX_ATTEMPTS) without a clean exit - stopping. See $LOG_DIR."
exit 1
