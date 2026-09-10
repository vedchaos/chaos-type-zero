"""
CHAOS TYPE ZERO 6-Agent OMO Sisyphus Orchestrator
Plan → Execute → Critique → Refine → Memory → Report
"""

import ast
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Import CHAOS TYPE ZERO modules
sys.path.insert(0, str(Path(__file__).parent))
from .smart_brain import get_brain
from .memory_3tier import get_memory

CTZ_ROOT = Path(__file__).parent.parent


class Agent:
    """Base agent class"""

    def __init__(self, name, role, soul_path=None):
        self.name = name
        self.role = role
        self.soul = self._load_soul(soul_path)
        self.brain = get_brain()
        self.memory = get_memory()

    def _load_soul(self, path):
        if path and Path(path).exists():
            return Path(path).read_text()
        return f"You are CHAOS TYPE ZERO {self.name}. Role: {self.role}"

    def think(self, context, task_type="agent"):
        """Use LLM to think about a task"""
        prompt = f"Context: {json.dumps(context)}\n\nTask: {self.role}"
        response, provider, model, cached = self.brain.query(prompt, task_type)
        return {
            "response": response,
            "provider": provider,
            "model": model,
            "cached": cached,
        }


class PlannerAgent(Agent):
    """Breaks tasks into steps, creates execution plan"""

    def __init__(self):
        super().__init__("Planner", "Break user request into clear, ordered steps")

    def plan(self, user_request, context=None):
        prompt = f"""Analyze this request and create a step-by-step execution plan.

Request: {user_request}

Context: {json.dumps(context or {})}

Return a JSON plan with:
- steps: array of {{id, action, tool, args, depends_on}}
- estimated_time: seconds
- risk_level: low/medium/high
- requires_authorization: boolean"""

        result = self.think(prompt, task_type="agent")

        try:
            plan = json.loads(result["response"])
        except (json.JSONDecodeError, TypeError):
            plan = {
                "steps": [{"id": 1, "action": result["response"], "tool": "general", "args": {}}],
                "estimated_time": 30,
                "risk_level": "low",
                "requires_authorization": False,
            }

        # Validate plan structure
        if "steps" not in plan:
            plan["steps"] = [{"id": 1, "action": str(plan), "tool": "general", "args": {}}]
        if "risk_level" not in plan:
            plan["risk_level"] = "low"

        return plan


class CoderAgent(Agent):
    """Writes and reviews code"""

    def __init__(self):
        super().__init__("Coder", "Write clean, efficient, well-documented code")

    def write_code(self, spec, language="python"):
        prompt = f"""Write {language} code for this specification:

{spec}

Requirements:
- Clean, readable code
- Proper error handling
- Comments where needed
- Follow best practices"""

        result = self.think(prompt, task_type="code")
        return result["response"]

    def review_code(self, code):
        prompt = f"""Review this code for:
- Bugs and errors
- Security issues
- Performance problems
- Code quality

Code:
{code}

Return JSON with: issues[], suggestions[], score (1-10)"""

        result = self.think(prompt, task_type="code")
        try:
            return json.loads(result["response"])
        except (json.JSONDecodeError, TypeError):
            return {"issues": [], "suggestions": [result["response"]], "score": 7}


class ResearcherAgent(Agent):
    """Gathers information via web search, OSINT, databases"""

    def __init__(self):
        super().__init__("Researcher", "Gather accurate, relevant information")

    def research(self, query, context=None):
        prompt = f"""Research this topic thoroughly:

Query: {query}
Context: {json.dumps(context or {})}

Provide:
- Key findings
- Sources
- Confidence level
- Related information"""

        result = self.think(prompt, task_type="research")
        return {
            "findings": result["response"],
            "provider": result["provider"],
        }


class CriticAgent(Agent):
    """Reviews work, finds errors, suggests improvements"""

    def __init__(self):
        super().__init__("Critic", "Review work critically, find errors, suggest improvements")

    def review(self, work, criteria=None):
        prompt = f"""Critically review this work:

{json.dumps(work) if isinstance(work, dict) else work}

Criteria: {criteria or 'quality, accuracy, completeness, security'}

Return JSON with:
- score: 1-10
- issues: [{{severity, description, fix}}]
- strengths: [str]
- improvements: [str]
- pass: boolean (score >= 7)"""

        result = self.think(prompt, task_type="quality")
        try:
            return json.loads(result["response"])
        except (json.JSONDecodeError, TypeError):
            return {
                "score": 7,
                "issues": [],
                "strengths": ["Work completed"],
                "improvements": [result["response"]],
                "pass": True,
            }


class ExecutorAgent(Agent):
    """Runs commands, reads/writes files, dispatches to registered tools.

    Supports three execution modes via step['tool']:
    - 'shell': run a shell command (safe argument list, no shell=True)
    - 'read_file' / 'write_file': file I/O
    - anything else: LLM-assisted free-form execution
    """

    # Commands that are NEVER allowed (dangerous)
    BLOCKED_COMMANDS = {
        "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "> /dev/sda",
        "format c:", "shutdown", "reboot", "halt", "init 0",
    }

    def __init__(self):
        super().__init__("Executor", "Execute planned steps efficiently")

    # ---- shell execution ----
    def _run_shell(self, cmd, timeout=30):
        """Run a shell command safely."""
        cmd_lower = cmd.lower().strip()
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return {"status": "blocked", "output": f"Dangerous command blocked: {blocked}"}

        try:
            if os.name == "nt":
                # Native Windows PowerShell support
                shell_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd]
            else:
                shell_cmd = ["bash", "-c", cmd]

            result = subprocess.run(
                shell_cmd,
                capture_output=True, text=True, timeout=timeout, check=False
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "output": result.stdout[:5000],
                "error": result.stderr[:2000] if result.stderr else "",
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "output": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"status": "error", "output": str(e)}

    # ---- file operations ----
    def _read_file(self, path):
        p = Path(path)
        if not p.exists():
            return {"status": "error", "output": f"File not found: {path}"}
        if p.stat().st_size > 1_000_000:
            return {"status": "error", "output": "File too large (>1MB)"}
        return {"status": "success", "output": p.read_text(encoding="utf-8", errors="replace")}

    def _write_file(self, path, content):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"status": "success", "output": f"Written {len(content)} bytes to {path}"}

    # ---- main execute entry ----
    def execute(self, step, context=None):
        """Execute a single step.

        step format:
            {id, action, tool, args}
        tool can be:
            'shell'       → args: {command, timeout?}
            'read_file'   → args: {path}
            'write_file'  → args: {path, content}
            'general'/etc → LLM-assisted execution
        """
        tool = step.get("tool", "general")
        args = step.get("args", {})
        step_id = step.get("id", "?")
        action = step.get("action", "unknown")

        start = time.time()

        # --- shell ---
        if tool == "shell":
            cmd = args.get("command", action)
            timeout = args.get("timeout", 30)
            result = self._run_shell(cmd, timeout)

        # --- file ops ---
        elif tool == "read_file":
            result = self._read_file(args.get("path", ""))

        elif tool == "write_file":
            result = self._write_file(args.get("path", ""), args.get("content", ""))

        # --- LLM-assisted free-form ---
        else:
            result = self._llm_execute(action, args, context)

        elapsed = round(time.time() - start, 2)
        exec_status = result.get("status", "success")

        output_data = {
            "step_id": step_id,
            "action": action,
            "tool": tool,
            "status": exec_status,
            "output": result.get("output", ""),
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }

        # Cryptographic provenance receipt for consequential execution
        try:
            from .receipts import get_provenance
            receipt = get_provenance().create_receipt(
                task_id=f"step-{step_id}",
                task_desc=action,
                agent_from="Planner",
                agent_to="Executor",
                action_type="tool_execution",
                tool_name=tool,
                inputs=args,
                results={"output": result.get("output", "")[:500], "status": exec_status},
                status="executed" if exec_status == "success" else exec_status
            )
            output_data["receipt"] = receipt
        except Exception:
            pass

        return output_data

    @staticmethod
    def _is_safe_code(code: str):
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"SyntaxError in generated code: {e}"

        forbidden_calls = {"eval", "exec", "__import__", "compile"}
        forbidden_modules = {"shutil", "ctypes", "subprocess", "socket"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        return False, f"Forbidden module import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module in forbidden_modules:
                    return False, f"Forbidden module import: {node.module}"
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                    return False, f"Forbidden function call: {node.func.id}"
                elif isinstance(node.func, ast.Attribute) and node.func.attr in {"system", "popen", "spawn", "rmdir", "remove", "unlink"}:
                    return False, f"Forbidden dangerous call: {node.func.attr}"
        return True, "Safe"

    def _llm_execute(self, action, args, context=None):
        """Use LLM to generate and optionally run a solution."""
        prompt = (
            f"Action: {action}\n"
            f"Args: {json.dumps(args)}\n"
            f"Context: {json.dumps(context or {})}\n\n"
            f"Generate a Python one-liner or short script that accomplishes this. "
            f"Return ONLY the code, no explanation."
        )
        result = self.think(prompt, task_type="code")
        code = result.get("response", "").strip()

        # Try to extract code block
        code_match = re.search(r"```(?:python)?\s*\n(.*?)```", code, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()

        # Execute the generated code if it looks safe via AST inspection
        if code:
            is_safe, reason = self._is_safe_code(code)
            if not is_safe:
                return {"status": "blocked", "output": f"Code blocked by AST safety inspector: {reason}"}
            try:
                exec_result = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True, text=True, timeout=30
                )
                return {
                    "status": "success" if exec_result.returncode == 0 else "error",
                    "output": exec_result.stdout[:3000] or exec_result.stderr[:2000],
                }
            except Exception as e:
                return {"status": "error", "output": f"Exec failed: {e}\nGenerated code:\n{code}"}

        return {"status": "success", "output": code}


class MemoryAgent(Agent):
    """Manages long-term memory, retrieval, storage"""

    def __init__(self):
        super().__init__("Memory", "Manage persistent memory across sessions")

    def remember(self, content, tags="", importance=0.5, mem_type="note"):
        """Save to memory"""
        mem_id = self.memory.save(content, tags, mem_type, importance)
        return {"saved": True, "memory_id": mem_id}

    def recall(self, query, limit=10):
        """Search memory"""
        results = self.memory.search(query, limit)
        return {"results": results, "count": len(results)}

    def summarize_session(self, conversation):
        """Summarize a session for memory"""
        prompt = f"""Summarize this conversation for long-term memory:

{json.dumps(conversation[-10:])}

Return key:
- decisions: [str]
- findings: [str]
- tasks_completed: [str]
- pending: [str]
- importance: 0.0-1.0"""

        result = self.think(prompt, task_type="write")
        try:
            return json.loads(result["response"])
        except (json.JSONDecodeError, TypeError):
            return {"summary": result["response"], "importance": 0.7}


# === Sisyphus Orchestrator ===
class SisyphusOrchestrator:
    """
    6-Agent OMO Sisyphus Loop:
    1. Observer: User input → understand
    2. Model: Create plan
    3. Operate: Execute plan
    4. Critic: Review output
    5. Refine: Fix issues (loop back to Operate)
    6. Memory: Save outcome
    7. Report: Return results
    """

    def __init__(self, adaptive=True, max_iterations=3):
        self.planner = PlannerAgent()
        self.coder = CoderAgent()
        self.researcher = ResearcherAgent()
        self.critic = CriticAgent()
        self.executor = ExecutorAgent()
        self.memory_agent = MemoryAgent()
        self.adaptive = adaptive  # Skip critique for simple tasks
        self.max_iterations = max_iterations

    def run(self, user_request, context=None):
        """Execute the full Sisyphus loop"""
        start_time = time.time()
        log = []

        # Step 1: PLAN
        log.append({"step": "plan", "time": time.time()})
        plan = self.planner.plan(user_request, context)
        log.append({"step": "plan_result", "plan": plan})

        # Step 2: EXECUTE
        results = []
        for step in plan.get("steps", []):
            log.append({"step": "execute", "step_id": step.get("id")})
            result = self.executor.execute(step, context)
            results.append(result)
        log.append({"step": "execute_results", "results": results})

        # Step 3: CRITIQUE (adaptive — skip for simple tasks)
        if self.adaptive and plan.get("risk_level") == "low" and len(plan.get("steps", [])) <= 2:
            critique = {"score": 9, "pass": True, "issues": []}
            log.append({"step": "critique_skipped", "reason": "simple_task"})
        else:
            log.append({"step": "critique"})
            critique = self.critic.review({"plan": plan, "results": results})
            log.append({"step": "critique_result", "critique": critique})

        # Step 4: REFINE (if needed) — actually apply fixes
        iterations = 0
        while not critique.get("pass", True) and iterations < self.max_iterations:
            iterations += 1
            log.append({"step": "refine", "iteration": iterations})

            # Fix issues
            fixed_outputs = []
            for issue in critique.get("issues", []):
                fix_spec = f"Fix this issue: {issue.get('description', '')}\nSuggested fix: {issue.get('fix', 'N/A')}"
                fix_result = self.executor.execute(
                    {"id": f"fix_{iterations}", "action": fix_spec, "tool": "general", "args": {}},
                    context
                )
                fixed_outputs.append(fix_result)

            # Add fixes to results
            results.extend(fixed_outputs)
            log.append({"step": "refine_results", "fixes": fixed_outputs})

            # Re-critique
            critique = self.critic.review({"plan": plan, "results": results})
            log.append({"step": "critique_result", "critique": critique})

        # Step 5: MEMORY
        log.append({"step": "memory"})
        memory_result = self.memory_agent.remember(
            f"Task: {user_request}\nResult: {json.dumps(results[:3])}",
            tags="task_outcome",
            importance=critique.get("score", 5) / 10.0,
            mem_type="task",
        )
        log.append({"step": "memory_result", "summary": memory_result})

        # Step 6: REPORT
        elapsed = time.time() - start_time
        report = {
            "request": user_request,
            "plan": plan,
            "results": results,
            "critique": critique,
            "iterations": iterations,
            "elapsed_seconds": round(elapsed, 2),
            "log": log,
        }

        return report


# === Singleton ===
_orchestrator = None

def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SisyphusOrchestrator()
    return _orchestrator


if __name__ == "__main__":
    orch = get_orchestrator()
    result = orch.run("Initialize CHAOS TYPE ZERO memory system and save a test entry")
    print(json.dumps(result, indent=2))
