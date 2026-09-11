# 🔥 CHAOS TYPE ZERO

[![GitHub stars](https://img.shields.io/github/stars/vedchaos/chaos-type-zero?style=flat-square&color=00ff41)](https://github.com/vedchaos/chaos-type-zero/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/vedchaos/chaos-type-zero?style=flat-square&color=00ff41)](https://github.com/vedchaos/chaos-type-zero/network/members)
[![GitHub issues](https://img.shields.io/github/issues/vedchaos/chaos-type-zero?style=flat-square&color=ff4444)](https://github.com/vedchaos/chaos-type-zero/issues)
[![GitHub license](https://img.shields.io/github/license/vedchaos/chaos-type-zero?style=flat-square&color=00ff41)](https://github.com/vedchaos/chaos-type-zero/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue?style=flat-square)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)]()
[![MCP](https://img.shields.io/badge/MCP-10%20Core%20Servers-orange?style=flat-square)](https://modelcontextprotocol.io/)
[![Tools](https://img.shields.io/badge/Tools-67%20Verified-green?style=flat-square)]()
[![Providers](https://img.shields.io/badge/Providers-14-purple?style=flat-square)]()
[![Provenance](https://img.shields.io/badge/Receipts-HMAC--SHA256-blueviolet?style=flat-square)]()
[![Tests](https://img.shields.io/badge/Tests-100%25%20passing-brightgreen?style=flat-square)]()
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](https://github.com/vedchaos/chaos-type-zero/blob/main/LICENSE)

> **C**omprehensive **H**ybrid **A**utonomous **O**perating **S**ystem — **Type Zero**

An autonomous, zero-bloat Agentic AI Operating System for software engineers, automation architects, and autonomous system builders. **10 focused Core MCP servers, 67 production-grade agentic tools, 14 LLM providers, cryptographic portable provenance receipts, 3-tier self-healing memory, cross-session context bridging, resilient zero-dependency encrypted vault, Kubernetes, Terraform, Prometheus, and Grafana.**

---

## ⚡ What is CHAOS TYPE ZERO?

CHAOS TYPE ZERO (CTZ) is an autonomous Agentic AI operating system that thinks, plans, executes, remembers, and audits its own actions. Built specifically to eliminate gimmick bloat and focus 100% on real agentic execution:

### 🌟 Core Capabilities

| Feature | What it does |
|---------|-------------|
| **10 Core Agentic MCP Servers** | Production tools: File, Git, Web, Real Playwright Browser, API Client, Automation, Context Bridge, Sisyphus Orchestrator, Encrypted Vault, and System Monitor |
| **67 Verified Agentic Tools** | Direct OS execution tools with JSON-RPC 2.0 stdio compliance |
| **Cryptographic Provenance Receipts** | Tamper-evident HMAC-SHA256 signed portable execution receipts for agent handoffs and tool actions |
| **14 LLM Providers** | Free-first dynamic routing with auto-fallback: Ollama, Groq, Gemini, DeepSeek, SambaNova, Cloudflare, HuggingFace, OpenAI, Anthropic, etc. |
| **3-Tier Memory Engine** | RAM LRU cache (instant) → SQLite structured storage (fast) → ChromaDB vector semantic search |
| **Cross-Session Context Bridge** | Persistent facts, session links, snapshot memories, and relationship chains across restarts |
| **Self-Healing Memory Healer** | Automatic SQLite PRAGMA integrity verification, index repair, deduplication, and optimization |
| **6-Agent Sisyphus Orchestrator** | Adaptive planning loop: Plan → Code → Research → Critic → Execute → Memory with AST safety sandbox |
| **Heuristics & Meta-Reasoner** | Task complexity scoring, 0–100 risk classification, USD cost estimation, and multi-strategy adaptive routing |
| **Resilient Encrypted Vault** | Secure credential management with AES-128 Fernet and zero-dependency standard library HMAC authenticated cipher fallback |
| **Real Browser Automation** | Headless or visual Playwright automation for scraping, navigation, forms, and JavaScript execution |
| **Full Automation Engine** | Interval, Cron (5-field syntax), File Watcher, and Webhook triggers with automated preset actions |
| **Observability & Telemetry** | Prometheus `/metrics` endpoint (port 9090) + Cyberpunk live WebSocket dashboard + Grafana 14-panel dashboard |
| **Cloud & DevOps Ready** | Production Kubernetes manifests (HPA, Ingress, RBAC), AWS Terraform IaC, Docker Compose, and CI/CD pipelines |

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
# Clone the repository
git clone https://github.com/vedchaos/chaos-type-zero.git
cd chaos-type-zero

# Windows Automated Setup
.\install.ps1

# Linux / macOS Setup
chmod +x install.sh && ./install.sh
```

### 2. Run the Master Full-Stack Audit

```bash
python verify_all.py
```
> Runs all 5 test pipelines: Core Unit Tests, 10 MCP Servers, Automation Engine, Context Bridge, and Advanced Agentic OS Verification in ~1.8s with zero failures.

### 3. Start the Dashboard & Metrics

```bash
# Cyberpunk WebSocket & REST Dashboard (Port 8080)
python dashboard/server.py

# Prometheus Metrics Exporter (Port 9090)
python bridge_core/prometheus_metrics.py
```

---

## 🏗️ System Architecture

```
CHAOS TYPE ZERO/
├── SOUL_CTZ.md                      ← Agent identity & operational doctrine (hot-reload)
├── opencode.json                    ← Clean OpenCode / MCP client configuration
├── verify_all.py                    ← Master 5-suite full-stack verifier
├── bridge_core/                     ← Core Operating System Engines
│   ├── smart_brain.py              ← 14 LLM providers, dynamic fallback & key rotation
│   ├── memory_3tier.py             ← RAM (LRU) + SQLite + ChromaDB semantic search
│   ├── agents.py                   ← 6-Agent Sisyphus orchestrator & AST sandbox
│   ├── task_classifier.py          ← 12 Task types with Hinglish natural language parsing
│   ├── scheduler.py                ← 5-field Cron parser & natural time expressions
│   ├── receipts.py                 ← Cryptographic provenance & signed receipts engine
│   ├── automation.py               ← Workflow triggers, action handlers & event engine
│   ├── context_bridge.py           ← Persistent cross-session facts & memory graph
│   ├── cache.py                    ← Multi-tiered response cache
│   ├── memory_healer.py            ← SQLite PRAGMA integrity checker & auto-repair
│   ├── vault.py                    ← Authenticated credential vault (Zero-dep stdlib fallback)
│   ├── heuristics.py               ← 0-100 Risk assessment & USD cost estimation
│   ├── meta_reasoner.py            ← Complexity analysis & multi-strategy planner
│   ├── neural.py                   ← Hebbian learning, classification & embeddings
│   └── prometheus_metrics.py       ← /metrics Prometheus scraping server (port 9090)
├── mcp_servers/                     ← 10 Production-Grade Agentic MCP Servers
│   ├── file_mcp.py                 ← File I/O, search, regex grep & metadata (8 tools)
│   ├── git_mcp.py                  ← Version control, commit, diff, status, log (7 tools)
│   ├── web_mcp.py                  ← Web requests, headers & DuckDuckGo search (3 tools)
│   ├── playwright_mcp.py           ← Real browser automation, clicks, forms, scraping (10 tools)
│   ├── api_mcp.py                  ← HTTP/REST endpoint testing & API caller (5 tools)
│   ├── automation_mcp.py           ← Workflows, triggers & automation presets (4 tools)
│   ├── context_bridge_mcp.py       ← Cross-session memory & key facts storage (12 tools)
│   ├── ctz_orchestrator_mcp.py     ← Multi-agent orchestration loop (8 tools)
│   ├── vault_mcp.py                ← Encrypted secrets, keys & tokens management (5 tools)
│   └── monitor_mcp.py              ← System CPU, RAM, disk & process monitoring (5 tools)
├── dashboard/                       ← Cyberpunk Web UI & Telemetry
│   ├── index.html                  ← Real-time dashboard with Chart.js
│   ├── server.py                   ← RFC 6455 WebSocket + REST API server
│   └── mobile_api.py               ← Mobile control REST API
├── tests/                           ← Zero-Dependency Test Suite
│   ├── run_all_tests.py            ← Unified test runner (0.3s)
│   ├── test_all_mcps.py            ← Introspection test for all MCP tools
│   ├── test_receipts.py            ← Cryptographic signature & tamper tests
│   ├── test_smart_brain.py         ← Provider failover tests
│   ├── test_memory_3tier.py        ← Memory tier tests
│   ├── test_heuristics.py          ← Risk & cost tests
│   ├── test_meta_reasoner.py       ← Adaptive routing tests
│   ├── test_neural.py              ← Embeddings & classification tests
│   ├── test_task_classifier.py    ← Natural language & Hinglish tests
│   └── test_dashboard.py           ← Dashboard API & AST safety tests
├── k8s/                             ← 11 Production Kubernetes Manifests
├── terraform/                       ← AWS IaC (VPC, EC2, S3, CloudWatch)
├── grafana/                         ← 14-Panel Grafana Monitoring Dashboard
├── mobile/                          ← React Native / Expo Mobile App
└── docker/                          ← Containerization (Dockerfile + Compose)
```

---

## 🔐 Cryptographic Provenance Receipts Engine

CHAOS TYPE ZERO introduces portable signed execution receipts for autonomous agents. Whenever an agent executes consequential tools or delegates actions, an immutable receipt is minted:

```json
{
  "receipt": {
    "receipt_id": "rcpt_1789108482_5d2922ce3de9",
    "timestamp": "2026-09-11T06:34:42.123456Z",
    "task_id": "task_deploy_042",
    "task_description": "Deploy service to Kubernetes namespace",
    "handoff": {
      "from_agent": "Planner",
      "to_agent": "Executor"
    },
    "action": {
      "action_type": "tool_execution",
      "tool_name": "ctz_file_write",
      "inputs_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "results_hash": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"
    },
    "status": "executed"
  },
  "signature": "3f8a92...hmac-sha256...",
  "signer_key_id": "key-8e1d2f0a"
}
```

- **Tamper Evidence**: Any modification to inputs, outputs, timestamps, or statuses immediately invalidates verification.
- **Audit Ledger**: All receipts are committed to `data/provenance/receipts.db` and queryable via `/api/receipts`.

---

## 🧰 The 10 Core Agentic MCP Servers

| Server | Tools | Key Functions |
|---|---|---|
| `ctz-file` | 8 | `ctz_file_read`, `ctz_file_write`, `ctz_file_list`, `ctz_file_search`, `ctz_file_grep`, `ctz_file_info`, `ctz_file_copy`, `ctz_file_delete` |
| `ctz-git` | 7 | `ctz_git_status`, `ctz_git_diff`, `ctz_git_log`, `ctz_git_commit`, `ctz_git_add`, `ctz_git_branch`, `ctz_git_checkout` |
| `ctz-web` | 3 | `ctz_web_fetch`, `ctz_web_search` (DuckDuckGo integration), `ctz_web_headers` |
| `ctz-playwright` | 10 | `ctz_pw_open`, `ctz_pw_click`, `ctz_pw_type`, `ctz_pw_scrape`, `ctz_pw_screenshot`, `ctz_pw_fill_form`, `ctz_pw_wait`, `ctz_pw_execute_js`, `ctz_pw_navigate`, `ctz_pw_get_text` |
| `ctz-api` | 5 | `ctz_api_get`, `ctz_api_post`, `ctz_api_headers`, `ctz_api_ping`, `ctz_api_download` |
| `ctz-automation` | 4 | `ctz_auto_list`, `ctz_auto_create`, `ctz_auto_run`, `ctz_auto_stats` |
| `ctz-context-bridge` | 12 | `ctz_bridge_start_session`, `ctz_bridge_save_context`, `ctz_bridge_save_fact`, `ctz_bridge_search_facts`, `ctz_bridge_restore`, `ctz_bridge_end_session` |
| `ctz-orchestrator` | 8 | `ctz_orch_plan`, `ctz_orch_execute`, `ctz_orch_status`, `ctz_orch_history`, `ctz_orch_cancel`, `ctz_orch_agents` |
| `ctz-vault` | 5 | `ctz_vault_set`, `ctz_vault_get`, `ctz_vault_delete`, `ctz_vault_list`, `ctz_vault_stats` |
| `ctz-monitor` | 5 | `ctz_monitor_system`, `ctz_monitor_processes`, `ctz_monitor_disk`, `ctz_monitor_network`, `ctz_monitor_db_size` |

---

## 🧠 14 LLM Providers (Free-First Fallback)

| Priority | Provider | Model | Tier |
|---|---|---|---|
| 1 | **Ollama** | `llama3.1` | Local & Free (Zero Cost) |
| 2 | **Groq** | `llama-3.3-70b-versatile` | Ultra-fast Free Tier |
| 3 | **SambaNova** | `Meta-Llama-3.1-70B-Instruct` | High-speed Free Tier |
| 4 | **Cloudflare Workers AI** | `@cf/meta/llama-3.1-8b-instruct` | 10k req/day Free Tier |
| 5 | **Google Gemini** | `gemini-1.5-flash` | Free Tier (Multimodal) |
| 6 | **HuggingFace** | Free Inference API | Open Source Models |
| 7 | **DeepSeek** | `deepseek-chat` | Code Specialist (Ultra low cost) |
| 8 | **NVIDIA NIM** | `meta/llama-3.1-70b-instruct` | High Quality Free Tier |
| 9 | **Mistral** | `mistral-small` | Fast & Multilingual |
| 10 | **Cohere** | `command-r` | Enterprise Reasoning |
| 11 | **Together AI** | Open-source mixture | Pay-per-token Fallback |
| 12 | **OpenRouter** | Multi-model aggregation | Multi-provider Fallback |
| 13 | **OpenAI** | `gpt-4o` | Paid Enterprise Grade |
| 14 | **Anthropic** | `claude-3-5-sonnet` | Deep Analytical Reasoning |

---

## 🧪 Testing & Verification

CTZ includes a multi-tiered test harness designed to run with **zero required external dependencies**:

```bash
# 1. Master System Verifier (All 5 Pipelines)
python verify_all.py

# 2. Unified Core Unit & MCP Tool Discovery
python tests/run_all_tests.py

# 3. Context Bridge Session Persistence
python test_context_bridge.py

# 4. Background Automation Engine
python test_automation.py

# 5. Advanced Agentic OS Modules & MCP stdio Handshake
python test_v2.py
```

### Verified Test Results

```
=================================================================
  🏆 MASTER AUDIT SUMMARY REPORT
=================================================================
  ✅ Core Unit & MCP Suite            | PASSED   (0.46s)
  ✅ Automation Engine Suite          | PASSED   (0.25s)
  ✅ Context Bridge Persistence       | PASSED   (0.20s)
  ✅ CTZ v1 Core System Pipeline      | PASSED   (0.12s)
  ✅ CTZ v2 Advanced OS Verification  | PASSED   (1.16s)
=================================================================
  🎉 STATUS: 100% OPERATIONAL — ALL SUITES VERIFIED AND PASSING!
```

---

## 📜 License

[MIT License](LICENSE) — Copyright (c) 2026 Ved. Built with passion for autonomous intelligence.
