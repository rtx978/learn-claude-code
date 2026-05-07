#!/usr/bin/env python3
# Harness: context isolation -- protecting the model's clarity of thought.
"""
s04_subagent.py - Subagents

Spawn a child agent with fresh messages=[]. The child works in its own
context, sharing the filesystem, then returns only a summary to the parent.

    Parent agent                     Subagent
    +------------------+             +------------------+
    | messages=[...]   |             | messages=[]      |  <-- fresh
    |                  |  dispatch   |                  |
    | tool: task       | ---------->| while tool_use:  |
    |   prompt="..."   |            |   call tools     |
    |   description="" |            |   append results |
    |                  |  summary   |                  |
    |   result = "..." | <--------- | return last text |
    +------------------+             +------------------+
              |
    Parent context stays clean.
    Subagent context is discarded.

Key insight: "Process isolation gives context isolation for free."
"""
import json
import sys
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from fnmatch import fnmatch
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]
SKILLS_DIR = WORKDIR / "skills"
# -- Permission modes --
# Teaching version starts with three clear modes first.
MODES = ("default", "plan", "auto")
READ_ONLY_TOOLS = {"read_file", "bash_readonly"}
# Tools that modify state
WRITE_TOOLS = {"write_file", "edit_file", "bash"}
TRUST_MARKER = WORKDIR / ".claude" / ".claude_trusted"

#=====================================导包

from s03_todo_write import TodoManager
from s05_skill_loading import SkillLoader
import s06_context_compact
from access import PermissionManager,BashSecurityValidator
from hook import HookManager
from memory import MemoryManager,DreamConsolidator,MEMORY_GUIDANCE 
from Task import TaskManager,TASKS_DIR
from background_task import NotificationQueue, BackgroundManager
from cron_scheduler import CronScheduler
from agent_team import (
    TeammateManager,
    MessageBus,
    VALID_MSG_TYPES,
    INBOX_DIR,
    TEAM_DIR,
    REQUEST_STORE,
)
TASKS = TaskManager(TASKS_DIR)
TODO = TodoManager()
SKILL_LOADER = SkillLoader(SKILLS_DIR)
bash_validator = BashSecurityValidator()
'''多agent '''
BUS = MessageBus(INBOX_DIR)
TEAM = TeammateManager(TEAM_DIR)
SYSTEM = f"You are a coding agent at {WORKDIR}. Use the task tool to delegate exploration or subtasks."
SUBAGENT_SYSTEM = f"You are a coding subagent at {WORKDIR}. Complete the given task, then summarize your findings."

#记忆系统，跨任务记忆
memory_mgr = MemoryManager()
#后台任务
BG = BackgroundManager()
#定时任务
scheduler = CronScheduler()
def run_save_memory(name: str, description: str, mem_type: str, content: str) -> str:
    return memory_mgr.save_memory(name, description, mem_type, content)
# -- Tool implementations shared by parent and child --
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    encoding = "utf-8" if sys.platform != "win32" else "gbk"
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding=encoding,  # 强制指定编码
        errors="replace"    # 无法解码的字符自动替换，不报错
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    REQUEST_STORE.create({
        "request_id": req_id,
        "kind": "shutdown",
        "from": "lead",
        "to": teammate,
        "status": "pending",
        "created_at": time.time(),
        "updated_at": time.time(),
    })
    BUS.send(
        "lead", teammate, "Please shut down gracefully.",
        "shutdown_request", {"request_id": req_id},
    )
    return f"Shutdown request {req_id} sent to '{teammate}' (status: pending)"


def handle_plan_review(request_id: str, approve: bool, feedback: str = "") -> str:
    req = REQUEST_STORE.get(request_id)
    if not req:
        return f"Error: Unknown plan request_id '{request_id}'"
    updated = REQUEST_STORE.update(
        request_id,
        status="approved" if approve else "rejected",
        reviewed_by="lead",
        resolved_at=time.time(),
        feedback=feedback,
    )
    BUS.send(
        "lead", req["from"], feedback, "plan_approval_response",
        {"request_id": request_id, "approve": approve, "feedback": feedback},
    )
    return f"Plan {updated['status']} for '{req['from']}'"


def check_shutdown_status(request_id: str) -> str:
    return json.dumps(REQUEST_STORE.get(request_id) or {"error": "not found"})


def build_system_prompt() -> str:
    parts = [
        f"You are a team lead and coding agent at {WORKDIR}. "
        f"Spawn teammates, communicate via inboxes, and use tools to solve tasks."
        f"Skills available:{SKILL_LOADER.get_descriptions()}"
    ]

    memory_section = memory_mgr.load_memory_prompt()
    if memory_section:
        parts.append(memory_section)

    parts.append(MEMORY_GUIDANCE)
    return "\n\n".join(parts)

TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "todo":       lambda **kw: TODO.update(kw["items"]),
    "load_skill": lambda **kw: SKILL_LOADER.get_content(kw["name"]),
    "compact":    lambda **kw: "Manual compression requested.",
    "save_memory":  lambda **kw: run_save_memory(kw["name"], kw["description"], kw["type"], kw["content"]),
    "task_create": lambda **kw: TASKS.create(kw["subject"], kw.get("description", "")),
    "task_update": lambda **kw: TASKS.update(kw["task_id"], kw.get("status"), kw.get("owner"), kw.get("addBlockedBy"), kw.get("addBlocks")),
    "task_list":   lambda **kw: TASKS.list_all(),
    "task_get":    lambda **kw: TASKS.get(kw["task_id"]),
    "background_run":   lambda **kw: BG.run(kw["command"]),
    "check_background": lambda **kw: BG.check(kw.get("task_id")),
    "cron_create": lambda **kw: scheduler.create(
        kw["cron"], kw["prompt"], kw.get("recurring", True), kw.get("durable", False)),
    "cron_delete": lambda **kw: scheduler.delete(kw["id"]),
    "cron_list":   lambda **kw: scheduler.list_tasks(),
    "spawn_teammate":  lambda **kw: TEAM.spawn(kw["name"], kw["role"], kw["prompt"]),
    "list_teammates":  lambda **kw: TEAM.list_all(),
    "send_message":    lambda **kw: BUS.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
    "read_inbox":      lambda **kw: json.dumps(BUS.read_inbox("lead"), indent=2),
    "broadcast":       lambda **kw: BUS.broadcast("lead", kw["content"], TEAM.member_names()),
    "shutdown_request": lambda **kw: handle_shutdown_request(kw["teammate"]),
    "shutdown_response": lambda **kw: check_shutdown_status(kw.get("request_id", "")),
    "plan_approval":   lambda **kw: handle_plan_review(kw["request_id"], kw["approve"], kw.get("feedback", "")),
}

# Child gets all base tools except task (no recursive spawning)
CHILD_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "save_memory", "description": "Save a persistent memory that survives across sessions.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "Short identifier (e.g. prefer_tabs, db_schema)"},
         "description": {"type": "string", "description": "One-line summary of what this memory captures"},
         "type": {"type": "string", "enum": ["user", "feedback", "project", "reference"],
                  "description": "user=preferences, feedback=corrections, project=non-obvious project conventions or decision reasons, reference=external resource pointers"},
         "content": {"type": "string", "description": "Full memory content (multi-line OK)"},
     }, "required": ["name", "description", "type", "content"]}},
    {"name": "shutdown_request", "description": "Request a teammate to shut down gracefully. Returns a request_id for tracking.",
     "input_schema": {"type": "object", "properties": {"teammate": {"type": "string"}}, "required": ["teammate"]}},
    {"name": "shutdown_response", "description": "Check the status of a shutdown request by request_id.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}}, "required": ["request_id"]}},
    {"name": "plan_approval", "description": "Approve or reject a teammate's plan. Provide request_id + approve + optional feedback.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "feedback": {"type": "string"}}, "required": ["request_id", "approve"]}},
]


# -- Subagent: fresh context, filtered tools, summary-only return --
def run_subagent(prompt: str, hooks: HookManager | None = None) -> str:
    sub_messages = [{"role": "user", "content": prompt}]  # fresh context
    for _ in range(30):  # safety limit
        response = client.messages.create(
            model=MODEL, system=SUBAGENT_SYSTEM, messages=sub_messages,
            tools=CHILD_TOOLS, max_tokens=8000,
        )
        sub_messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_input = dict(block.input or {})
            ctx = {"tool_name": block.name, "tool_input": tool_input}
            if hooks:
                pre_result = hooks.run_hooks("PreToolUse", ctx)
                for msg in pre_result.get("messages", []):
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"[Hook message]: {msg}",
                    })
                if pre_result.get("blocked"):
                    reason = pre_result.get("block_reason", "Blocked by hook")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Tool blocked by PreToolUse hook: {reason}",
                    })
                    continue
                tool_input = ctx["tool_input"]
            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**tool_input) if handler else f"Unknown tool: {block.name}"
            if hooks:
                ctx["tool_output"] = output
                post_result = hooks.run_hooks("PostToolUse", ctx)
                for msg in post_result.get("messages", []):
                    output += f"\n[Hook note]: {msg}"
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)[:50000]})
        sub_messages.append({"role": "user", "content": results})
    # Only the final text returns to the parent -- child context is discarded
    return "".join(b.text for b in response.content if hasattr(b, "text")) or "(no summary)"


# -- Parent tools: base tools + task dispatcher --
PARENT_TOOLS = CHILD_TOOLS + [
    {"name": "task", "description": "Spawn a subagent with fresh context. It shares the filesystem but not conversation history.",
     "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}, "description": {"type": "string", "description": "Short description of the task"}}, "required": ["prompt"]}},
    {"name": "todo", "description": "Update task list. Track progress on multi-step tasks.",
     "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["id", "text", "status"]}}}, "required": ["items"]}},
    {"name": "load_skill", "description": "Load specialized knowledge by name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string", "description": "Skill name to load"}}, "required": ["name"]}},
    {"name": "compact", "description": "Trigger manual conversation compression.",
     "input_schema": {"type": "object", "properties": {"focus": {"type": "string", "description": "What to preserve in the summary"}}}},
    {"name": "task_create", "description": "Create a new task.",
     "input_schema": {"type": "object", "properties": {"subject": {"type": "string"}, "description": {"type": "string"}}, "required": ["subject"]}},
    {"name": "task_update", "description": "Update a task's status, owner, or dependencies.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]}, "owner": {"type": "string", "description": "Set when a teammate claims the task"}, "addBlockedBy": {"type": "array", "items": {"type": "integer"}}, "addBlocks": {"type": "array", "items": {"type": "integer"}}}, "required": ["task_id"]}},
    {"name": "task_list", "description": "List all tasks with status summary.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "task_get", "description": "Get full details of a task by ID.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
    {"name": "background_run", "description": "Run command in background thread. Returns task_id immediately.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "check_background", "description": "Check background task status. Omit task_id to list all.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}}},
    {"name": "cron_create", "description": "Schedule a recurring or one-shot task with a cron expression.",
     "input_schema": {"type": "object", "properties": {
         "cron": {"type": "string", "description": "5-field cron expression: 'min hour dom month dow'"},
         "prompt": {"type": "string", "description": "The prompt to inject when the task fires"},
         "recurring": {"type": "boolean", "description": "true=repeat, false=fire once then delete. Default true."},
         "durable": {"type": "boolean", "description": "true=persist to disk, false=session-only. Default false."},
     }, "required": ["cron", "prompt"]}},
    {"name": "cron_delete", "description": "Delete a scheduled task by ID.",
     "input_schema": {"type": "object", "properties": {
         "id": {"type": "string", "description": "Task ID to delete"},
     }, "required": ["id"]}},
    {"name": "cron_list", "description": "List all scheduled tasks.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "spawn_teammate", "description": "Spawn a persistent teammate that runs in its own thread.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "List all teammates with name, role, status.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_message", "description": "Send a message to a teammate's inbox.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
    {"name": "read_inbox", "description": "Read and drain the lead's inbox.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast", "description": "Send a message to all teammates.",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
]


def agent_loop(messages: list, perms: PermissionManager, hooks: HookManager):
    rounds_since_todo = 0

    while True:
        inbox = BUS.read_inbox("lead")
        if inbox:
            messages.append({
                "role": "user",
                "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>",
            })
        # Drain scheduled task notifications
        notifications = scheduler.drain_notifications()
        for note in notifications:
            print(f"[Cron notification] {note[:100]}")
            messages.append({"role": "user", "content": note})
        notifs = BG.drain_notifications()
        if notifs and messages:
            notif_text = "\n".join(
                f"[bg:{n['task_id']}] {n['status']}: {n['preview']} "
                f"(output_file={n['output_file']})"
                for n in notifs
            )
            messages.append({"role": "user", "content": f"<background-results>\n{notif_text}\n</background-results>"})
        # Layer 1: micro_compact before each LLM call
        s06_context_compact.micro_compact(messages)
        # Layer 2: auto_compact if token estimate exceeds threshold
        if s06_context_compact.estimate_tokens(messages) > s06_context_compact.THRESHOLD:
            print("[auto_compact triggered]")
            messages[:] = s06_context_compact.auto_compact(messages)
        system = build_system_prompt()
        response = client.messages.create(
            model=MODEL, system=system, messages=messages,
            tools=PARENT_TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return
        results = []
        used_todo = False
        manual_compact = False
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_input = dict(block.input or {})
            ctx = {"tool_name": block.name, "tool_input": tool_input}
            pre_result = hooks.run_hooks("PreToolUse", ctx)
            for msg in pre_result.get("messages", []):
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"[Hook message]: {msg}",
                })
            if pre_result.get("blocked"):
                reason = pre_result.get("block_reason", "Blocked by hook")
                output = f"Tool blocked by PreToolUse hook: {reason}"
                print(f"  [HOOK BLOCKED] {block.name}: {reason}")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
                continue
            tool_input = ctx["tool_input"]

            decision = perms.check(block.name, tool_input)
            if decision["behavior"] == "deny":
                output = f"Permission denied: {decision['reason']}"
                print(f"  [DENIED] {block.name}: {decision['reason']}")
            elif decision["behavior"] == "ask":
                if perms.ask_user(block.name, tool_input):
                    handler = TOOL_HANDLERS.get(block.name)
                    output = handler(**tool_input) if handler else f"Unknown: {block.name}"
                    print(f"> {block.name}: {str(output)[:200]}")
                else:
                    output = f"Permission denied by user for {block.name}"
                    print(f"  [USER DENIED] {block.name}")
            elif block.name == "task":
                desc = tool_input.get("description", "subtask")
                prompt = tool_input.get("prompt", "")
                print(f"> task ({desc}): {prompt[:80]}")
                output = run_subagent(prompt, hooks)
            elif block.name=="compact":
                manual_compact = True
                output = "Compressing...==="
            else:
                handler = TOOL_HANDLERS.get(block.name)
                output = handler(**tool_input) if handler else f"Unknown tool: {block.name}"
                if block.name == "todo":
                    used_todo = True
            ctx["tool_output"] = output
            post_result = hooks.run_hooks("PostToolUse", ctx)
            for msg in post_result.get("messages", []):
                output += f"\n[Hook note]: {msg}"
            print(f"> {block.name}:")
            print(f"  {str(output)[:200]}")
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
        rounds_since_todo = 0 if used_todo else rounds_since_todo + 1  #\todo的部分
        if rounds_since_todo >= 3:
            results.append({"type": "text", "text": "<reminder>Update your todos.</reminder>"})
        messages.append({"role": "user", "content": results})
        # Layer 3: manual compact triggered by the compact tool
        if manual_compact:#压缩的部分
            print("[manual compact]")
            messages[:] = s06_context_compact.auto_compact(messages)
            return


if __name__ == "__main__":
    scheduler.start()
    print("[Cron scheduler running. Background checks every second.]")
    print("[Commands: /cron to list tasks, /test to fire a test notification]")
    #权限系统
    print("Permission modes: default, plan, auto")
    mode_input = input("Mode (default): ").strip().lower() or "default"
    if mode_input not in MODES:
        mode_input = "default"
    perms = PermissionManager(mode=mode_input)
    #hook系统
    hooks = HookManager()
    hooks.run_hooks("SessionStart", {"tool_name": "", "tool_input": {}})
    print(f"[Permission mode: {mode_input}]")
    #记忆系统
    memory_mgr.load_all()
    mem_count = len(memory_mgr.memories)
    if mem_count:
        print(f"[{mem_count} memories loaded into context]")
    else:
        print("[No existing memories. The agent can create them with save_memory.]")
    history = []
    while True:
        try:
            query = input("\033[36ms04 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        # /mode command to switch modes at runtime
        if query.startswith("/mode"):
            parts = query.split()
            if len(parts) == 2 and parts[1] in MODES:
                perms.mode = parts[1]
                print(f"[Switched to {parts[1]} mode]")
            else:
                print(f"Usage: /mode <{'|'.join(MODES)}>")
            continue
        # /rules command to show current rules
        if query.strip() == "/rules":
            for i, rule in enumerate(perms.rules):
                print(f"  {i}: {rule}")
            continue
        if query.strip() == "/memories":
            if memory_mgr.memories:
                for name, mem in memory_mgr.memories.items():
                    print(f"  [{mem['type']}] {name}: {mem['description']}")
            else:
                print("  (no memories)")
            continue
        if query.strip() == "/team":
            print(TEAM.list_all())
            continue
        if query.strip() == "/inbox":
            print(json.dumps(BUS.read_inbox("lead"), indent=2))
            continue
        history.append({"role": "user", "content": query})
        agent_loop(history, perms, hooks)
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if hasattr(block, "text"):
                    print(block.text)
        print()
