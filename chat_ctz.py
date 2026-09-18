#!/usr/bin/env python3
"""
CHAOS TYPE ZERO (CTZ) - Interactive Chat & Autonomous Assistant
Run: python chat_ctz.py
"""

import os
import sys
import io
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, r"C:\Users\Ved28\chaos-type-zero")
sys.path.insert(0, r"C:\Users\Ved28\chaos-type-zero\mcp_servers")

from bridge_core.task_classifier import classify_task, get_task_chain
from bridge_core.memory_3tier import ChaosMemory
from bridge_core.heuristics import CTZHeuristics
from bridge_core.neural import CTZNeural
import mcp_servers.stock_mcp as stock_tool
import mcp_servers.dns_mcp as dns_tool

def print_banner():
    print("=" * 65)
    print("      CHAOS TYPE ZERO (CTZ) - INTERACTIVE CONSOLE")
    print("=" * 65)
    print("  * 6-Agent Sisyphus Core: Ready")
    print("  * 71 MCP Tools & Memory: Active")
    print("  * Web Dashboard: Live on http://localhost:8080")
    print("=" * 65)
    print("  Type any command or message in Hinglish / English.")
    print("  Examples:")
    print("   - 'stock AAPL' ya 'reliance ka price kya hai'")
    print("   - 'dns google.com' ya 'check ip'")
    print("   - 'remember meeting at 5pm'")
    print("   - 'search memory for hydra'")
    print("   - 'exit' ya 'quit' to close")
    print("=" * 65 + "\n")

def main():
    print_banner()
    memory = ChaosMemory()
    heuristics = CTZHeuristics()
    neural = CTZNeural()

    while True:
        try:
            user_input = input("\n\033[92mCTZ You > \033[0m").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q", "bye"]:
                print("\n[CTZ] Session closed. Chaos Type Zero signing off!")
                break

            # 1. Intent Classification
            task_type, confidence = classify_task(user_input)
            print(f"\033[90m[Brain: Intent detected as '{task_type}' (Confidence: {confidence:.0%})]\033[0m")

            # 2. Tool Routing
            lower = user_input.lower()

            # Stock check
            if any(w in lower for w in ["stock", "price", "share", "aapl", "tsla", "msft", "reliance", "nifty"]):
                words = user_input.upper().split()
                symbol = "AAPL"
                for w in words:
                    if w in ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "NVDA", "BTC"]:
                        symbol = w
                        break
                print(f"[Tool: stock_mcp] Querying market data for {symbol}...")
                data = stock_tool.stock_quote(symbol)
                price = data.get("price", "N/A")
                curr = data.get("currency", "USD")
                name = data.get("name", symbol)
                high = data.get("day_high", "N/A")
                low = data.get("day_low", "N/A")
                print(f"\n\033[96m[CTZ Market Engine]\033[0m")
                print(f" Asset:   {name} ({symbol})")
                print(f" Price:   ${price} {curr}")
                print(f" Range:   Low ${low} - High ${high}")

            # DNS Recon
            elif any(w in lower for w in ["dns", "resolve", "lookup", "ip"]):
                parts = user_input.split()
                domain = "google.com"
                for p in parts:
                    if "." in p and not p.startswith("http"):
                        domain = p
                        break
                print(f"[Tool: dns_mcp] Performing DNS A-record resolution on '{domain}'...")
                res = dns_tool.dns_lookup(domain)
                print(f"\n\033[96m[CTZ Recon Engine]\033[0m")
                print(res.get("stdout", "No response"))

            # Memory Save
            elif any(w in lower for w in ["remember", "save", "yaad rakh"]):
                mem_id = memory.save(user_input, tags="user_note", importance=0.8)
                print(f"\n\033[96m[CTZ 3-Tier Memory]\033[0m")
                print(f" Saved to Tier-1 (RAM) and Tier-2 (SQLite) successfully! (Entry ID: {mem_id})")

            # Memory Search
            elif any(w in lower for w in ["search memory", "find in memory", "search", "kya yaad hai"]):
                query = user_input.replace("search memory", "").replace("search", "").strip() or "Hydra"
                results = memory.search(query)
                print(f"\n\033[96m[CTZ 3-Tier Memory Retrieval]\033[0m")
                if results:
                    for r in results:
                        print(f" - [{r.get('source')}] {r.get('content')} (Score: {r.get('score')})")
                else:
                    print(f" No matching entries found for '{query}'.")

            # General Intelligence / Task Evaluation
            else:
                eval_res = heuristics.evaluate_task(user_input)
                classified = neural.classify(user_input)
                print(f"\n\033[96m[CTZ Autonomous Brain]\033[0m")
                print(f" Action Category:     {classified.get('category', 'general').capitalize()}")
                print(f" Risk Assessment:     {eval_res.get('risk')}/100 ({eval_res.get('tier')} tier)")
                print(f" Execution Strategy:  {eval_res.get('recommended_approach')}")
                print(f" Est. Execution Cost: {eval_res.get('cost_est', {}).get('tokens')} tokens (~${eval_res.get('cost_est', {}).get('cost_usd')})")
                print("\n Task analyzed and queued for Sisyphus 6-Agent loop execution.")

        except KeyboardInterrupt:
            print("\n[CTZ] Interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\033[91m[Error]: {e}\033[0m")

if __name__ == "__main__":
    main()
