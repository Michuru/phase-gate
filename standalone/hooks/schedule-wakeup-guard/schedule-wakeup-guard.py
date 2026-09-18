"""PreToolUse hook: block a ScheduleWakeup call made outside a real /loop
session. If your own history shows a recurring pattern of an agent calling
ScheduleWakeup as a general "check back on this later" mechanism -- rather
than /loop's actual dynamic-pacing use -- a written rule alone may not be
enough to change in-the-moment tool selection; this is the technical
backstop, same rationale as block-dangerous-commands.py.

Ground truth here was verified live (not guessed) via a throwaway `claude
-p` session with a debug PreToolUse hook logging its own stdin, plus direct
inspection of real sessions' own transcript files:
  - The PreToolUse payload has no field marking "session is in /loop
    dynamic mode" -- session_id/transcript_path/cwd/permission_mode/
    tool_name/tool_input only. This script exists because that field
    doesn't exist.
  - A literal user-typed slash command appears in transcript_path's JSONL
    as a `{"type": "user", "message": {"content": "<command-name>/<name>
    </command-name>..."}}` entry, where `content` is a short string made
    up entirely of the `<command-message>`/`<command-name>`/
    `<command-args>` wrapper (tag order not guaranteed). The same
    mechanism applies to /loop.
  - A ScheduleWakeup({stop: true}) call appears as a `type: "assistant"`
    entry whose `message.content` list has a `{"type": "tool_use", "name":
    "ScheduleWakeup", "input": {"stop": true}}` element.
  - Naive raw-line substring matching on `<command-name>/loop</command-name>`
    produces false positives: this exact string can appear inside a Bash
    tool_use's own command text or a tool_result (e.g. a session
    inspecting transcript content while building or debugging a hook like
    this one) without any real /loop ever having been invoked. Fixed by
    parsing each line as JSON and checking the structured `type`/
    `message.content` fields directly, never a raw substring scan.

Allowed without reading the transcript at all:
  - stop:true (stopping a loop is always safe to allow, never blocked).
  - prompt == the literal '<<autonomous-loop>>' sentinel -- the documented
    marker for a cron-based autonomous loop, which may have no /loop
    command-name marker in its own transcript at all (it starts via a
    scheduled trigger, not a typed slash command). Trusting this
    self-declared value is a deliberate, narrower trade than also trying
    to verify cron state here -- it still closes off the actual misuse
    shape, which never uses this exact sentinel.

Otherwise: read transcript_path, parse each line as JSON, and find the
most recent genuine `/loop` command-name entry (a `type: "user"` entry
whose `message.content` contains `<command-name>/loop`) and the most
recent genuine ScheduleWakeup({stop: true}) tool_use. If no /loop entry
exists anywhere, deny. If the most recent one was already followed by a
stop with no later /loop invocation, that loop has ended -- deny too.

Fails open (allows) on any missing/unreadable transcript, unparseable
line, or other error -- this hook should never be the reason a legitimate
loop breaks; it exists to catch a specific misuse shape, not to be a hard
guarantee.

JSON contract: code.claude.com/docs/en/hooks.md.
"""
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if data.get("tool_name") != "ScheduleWakeup":
    sys.exit(0)

tool_input = data.get("tool_input") or {}


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


# Stopping a loop is always safe -- never block it.
if tool_input.get("stop"):
    sys.exit(0)

# The documented sentinel for a cron-based autonomous loop -- no /loop
# command-name marker is expected in its own transcript, so trust this
# self-declared value rather than trying to verify scheduler state here.
if tool_input.get("prompt") == "<<autonomous-loop>>":
    sys.exit(0)

transcript_path = data.get("transcript_path")
if not transcript_path:
    sys.exit(0)  # can't check -- fail open

try:
    with open(transcript_path, encoding="utf-8") as f:
        raw_lines = f.readlines()
except Exception:
    sys.exit(0)  # can't check -- fail open

last_loop_start = -1
last_stop = -1
for i, line in enumerate(raw_lines):
    try:
        entry = json.loads(line)
    except Exception:
        continue

    if entry.get("type") == "user":
        content = entry.get("message", {}).get("content")
        # A real command entry's content is entirely the <command-message>/
        # <command-name>/<command-args> wrapper -- order between
        # <command-message> and <command-name> isn't guaranteed, so check
        # for the tag anywhere in this short, wrapper-only string rather
        # than anchoring on a fixed prefix.
        if isinstance(content, str) and "<command-name>/loop" in content.lower():
            last_loop_start = i
        continue

    if entry.get("type") == "assistant":
        content = entry.get("message", {}).get("content")
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "ScheduleWakeup"
                    and isinstance(block.get("input"), dict)
                    and block["input"].get("stop") is True
                ):
                    last_stop = i

if last_loop_start == -1:
    deny(
        "Blocked: ScheduleWakeup was called but no /loop invocation was found anywhere in "
        "this session's transcript. ScheduleWakeup exists only for /loop's dynamic pacing -- "
        "never as a general 'check back on this background task later' mechanism (a "
        "background agent call notifies on its own when it finishes; no action is needed to "
        "wait on it). If you're genuinely just waiting on something, don't schedule a wakeup. "
        "If a recurring /loop is actually wanted, ask the user to invoke it."
    )

if last_stop > last_loop_start:
    deny(
        "Blocked: the most recent /loop in this session was already stopped "
        "(ScheduleWakeup({stop: true}) ran after it, with no later /loop invocation), so this "
        "ScheduleWakeup call isn't part of a live loop. If a new /loop is actually wanted, ask "
        "the user to invoke it again."
    )

sys.exit(0)
