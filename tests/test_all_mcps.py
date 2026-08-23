"""Comprehensive MCP Server Test — All 71 Servers."""
import sys
import os
import importlib
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# All 71 MCP servers
MCP_SERVERS = [
    "abuseipdb_mcp",
    "api_mcp",
    "automation_mcp",
    "aws_mcp",
    "backup_mcp",
    "browser_mcp",
    "cache_mcp",
    "censys_mcp",
    "cicd_mcp",
    "comms_mcp",
    "context_bridge_mcp",
    "ctz_orchestrator_mcp",
    "data_mcp",
    "db_mcp",
    "db_multi_mcp",
    "deploy_mcp",
    "discord_bot",
    "dns_mcp",
    "docker_mcp",
    "docs_mcp",
    "elasticsearch_mcp",
    "email_mcp",
    "file_mcp",
    "game_ai_mcp",
    "git_mcp",
    "github_mcp",
    "health_mcp",
    "huggingface_mcp",
    "i18n_mcp",
    "image_gen_mcp",
    "image_mcp",
    "ipinfo_mcp",
    "knowledge_graph_mcp",
    "kubernetes_mcp",
    "llm_fallback",
    "memory_mcp",
    "ml_mcp",
    "mongo_mcp",
    "monitor_mcp",
    "neural_mcp",
    "news_mcp",
    "notify_mcp",
    "nse_mcp",
    "ocr_mcp",
    "pdf_mcp",
    "pentest_mcp",
    "pinecone_mcp",
    "playwright_mcp",
    "plugin_mcp",
    "postgres_mcp",
    "real_security_mcp",
    "redis_mcp",
    "report_mcp",
    "rss_mcp",
    "shodan_mcp",
    "slack_bot",
    "status_mcp",
    "stock_mcp",
    "task_router_mcp",
    "telegram_mcp",
    "terraform_mcp",
    "test_mcp",
    "translate_mcp",
    "unified_control_mcp",
    "vault_mcp",
    "virustotal_mcp",
    "vision_mcp",
    "voice_mcp",
    "weather_mcp",
    "web_mcp",
    "whois_mcp",
]

results = {"passed": [], "failed": [], "errors": []}

for server_name in MCP_SERVERS:
    try:
        # Import the module
        module = importlib.import_module(f"mcp_servers.{server_name}")
        
        # Check it has content
        attrs = [a for a in dir(module) if not a.startswith('_')]
        
        # Count tools (functions)
        tools = [a for a in attrs if callable(getattr(module, a, None))]
        
        # Check for MCP tool definitions (list of tool dicts)
        tool_list = None
        for attr_name in ['TOOLS', 'tools', 'TOOL_LIST', 'tool_list', 'TOOLS_LIST']:
            if hasattr(module, attr_name):
                tool_list = getattr(module, attr_name)
                break
        
        tool_count = len(tool_list) if isinstance(tool_list, (list, dict)) else len(tools)
        
        results["passed"].append({
            "name": server_name,
            "tools": tool_count,
            "attrs": len(attrs)
        })
        print(f"  PASS {server_name:<30} -- {tool_count} tools, {len(attrs)} attrs")
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:80]}"
        results["failed"].append({
            "name": server_name,
            "error": error_msg
        })
        print(f"  FAIL {server_name:<30} -- {error_msg}")

# Summary
print("\n" + "=" * 60)
print(f"RESULTS: {len(results['passed'])} passed / {len(results['failed'])} failed / {len(MCP_SERVERS)} total")
print("=" * 60)

if results["failed"]:
    print("\nFAILED SERVERS:")
    for f in results["failed"]:
        print(f"  - {f['name']}: {f['error']}")

total_tools = sum(p["tools"] for p in results["passed"])
print(f"\nTotal tools found: {total_tools}")
print(f"Success rate: {len(results['passed'])}/{len(MCP_SERVERS)} ({len(results['passed'])*100//len(MCP_SERVERS)}%)")

# Exit with error code if any servers failed — ensures CI catches failures
if results["failed"]:
    print(f"\nERROR: {len(results['failed'])} MCP server(s) FAILED")
    sys.exit(1)
else:
    print(f"\nAll {len(MCP_SERVERS)} MCP servers PASSED")
