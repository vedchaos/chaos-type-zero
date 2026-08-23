#!/usr/bin/env python3
"""CTZ MCP — GitHub"""
import json, sys, subprocess

SERVER_INFO = {"name": "github-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "gh_repo_list", "description": "List repositories for the authenticated user/org.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 30}}, "required": []}},
    {"name": "gh_issue_list", "description": "List issues in a repository (repo like owner/name).", "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}, "limit": {"type": "integer", "default": 30}}, "required": ["repo"]}},
    {"name": "gh_issue_create", "description": "Create an issue in a repository.", "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string", "default": ""}}, "required": ["repo", "title"]}},
    {"name": "gh_pr_list", "description": "List pull requests in a repository.", "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}, "limit": {"type": "integer", "default": 30}}, "required": ["repo"]}},
    {"name": "gh_pr_create", "description": "Create a pull request (requires a pushed branch; base optional).", "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string", "default": ""}, "base": {"type": "string"}}, "required": ["repo", "title"]}},
    {"name": "gh_pr_merge", "description": "Merge a pull request by number (merge commit).", "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}, "number": {"type": "integer"}}, "required": ["repo", "number"]}},
    {"name": "gh_release_list", "description": "List releases in a repository.", "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["repo"]}},
    {"name": "gh_gist_create", "description": "Create a secret (or public) gist from content.", "inputSchema": {"type": "object", "properties": {"description": {"type": "string", "default": ""}, "content": {"type": "string"}, "public": {"type": "boolean", "default": False}}, "required": ["content"]}},
    {"name": "gh_search_repos", "description": "Search GitHub repositories.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, "required": ["query"]}},
    {"name": "gh_api", "description": "Call any GitHub REST/GraphQL API endpoint via gh api.", "inputSchema": {"type": "object", "properties": {"endpoint": {"type": "string"}}, "required": ["endpoint"]}},
]


def _run(args, timeout=60, input_text=None):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input_text)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Tool not installed"}


def gh_repo_list(limit=30):
    return _run(["gh", "repo", "list", "--limit", str(int(limit))], timeout=90)


def gh_issue_list(repo, limit=30):
    return _run(["gh", "issue", "list", "-R", repo, "--limit", str(int(limit))], timeout=90)


def gh_issue_create(repo, title, body=""):
    return _run(["gh", "issue", "create", "-R", repo, "-t", title, "-b", body], timeout=90)


def gh_pr_list(repo, limit=30):
    return _run(["gh", "pr", "list", "-R", repo, "--limit", str(int(limit))], timeout=90)


def gh_pr_create(repo, title, body="", base=None):
    cmd = ["gh", "pr", "create", "-R", repo, "-t", title, "-b", body]
    if base:
        cmd += ["--base", base]
    return _run(cmd, timeout=90)


def gh_pr_merge(repo, number):
    return _run(["gh", "pr", "merge", str(int(number)), "-R", repo, "--merge"], timeout=90)


def gh_release_list(repo, limit=10):
    return _run(["gh", "release", "list", "-R", repo, "--limit", str(int(limit))], timeout=90)


def gh_gist_create(description="", content="", public=False):
    cmd = ["gh", "gist", "create", "-d", description]
    if public:
        cmd.append("-p")
    cmd.append("-")
    return _run(cmd, input_text=content, timeout=90)


def gh_search_repos(query, limit=20):
    return _run(["gh", "search", "repos", query, "--limit", str(int(limit))], timeout=90)


def gh_api(endpoint):
    return _run(["gh", "api", endpoint], timeout=90)


HANDLERS = {
    "gh_repo_list": gh_repo_list,
    "gh_issue_list": gh_issue_list,
    "gh_issue_create": gh_issue_create,
    "gh_pr_list": gh_pr_list,
    "gh_pr_create": gh_pr_create,
    "gh_pr_merge": gh_pr_merge,
    "gh_release_list": gh_release_list,
    "gh_gist_create": gh_gist_create,
    "gh_search_repos": gh_search_repos,
    "gh_api": gh_api,
}


def handle_request(request):
    method = request.get("method", "")
    rid = request.get("id")
    if method.startswith("notifications/"):
        return None
    try:
        if method == "initialize":
            params = request.get("params") or {}
            result = {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name", "")
            args = params.get("arguments") or {}
            fn = HANDLERS.get(name)
            if fn is None:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
            try:
                out = fn(**args)
                is_error = isinstance(out, dict) and "error" in out
            except Exception as exc:
                out = {"error": f"{type(exc).__name__}: {exc}"}
                is_error = True
            result = {"content": [{"type": "text", "text": json.dumps(out, indent=2, default=str)}]}
            if is_error:
                result["isError"] = True
        else:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            print(json.dumps(resp))
            sys.stdout.flush()
