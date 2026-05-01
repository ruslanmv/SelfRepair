<p align="center">
  <img src="assets/banner.svg" alt="SelfRepair Repo Banner" width="100%" />
</p>

<p align="center">
  <a href="https://github.com/ruslanmv/SelfRepair-Repo/actions"><img src="https://img.shields.io/github/actions/workflow/status/ruslanmv/SelfRepair-Repo/pull-request-validation.yml?style=flat-square&logo=github&label=CI" alt="CI Status" /></a>
  <a href="https://pypi.org/project/selfrepair-repo/"><img src="https://img.shields.io/pypi/v/selfrepair-repo?style=flat-square&logo=pypi&logoColor=white" alt="PyPI" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12-blue?style=flat-square&logo=python&logoColor=white" alt="Python" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-green?style=flat-square" alt="License" /></a>
  <a href="#platforms"><img src="https://img.shields.io/badge/platforms-GitHub%20%7C%20GitLab%20%7C%20HuggingFace-blueviolet?style=flat-square" alt="Platforms" /></a>
</p>

<p align="center">
  <b>SelfRepair Repo is an open-source AI Secure Delivery Copilot for repository scanning, AI-assisted repair, validation, and audit-ready reporting.</b><br/>
  <sub>Built on a repository-health automation core and upgraded with FastAPI orchestration, secure delivery workflows, and agent-ready endpoints.</sub>
</p>

---

## 🛡️ Overview

SelfRepair Repo scans repositories, detects delivery risks, generates repairs with AI assistance, validates fixes, and returns an audit-ready report.

Built on top of the original repository-health engine, it keeps the existing strengths of repository discovery, scanning, healing, sandbox validation, and reporting, while adding a FastAPI backend, multi-agent orchestration, and a vendor-neutral `/v1/rpc` endpoint for agent and tool integration.

```
┌───────────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   Discover    │───▶│    Analyze     │───▶│     Heal      │───▶│    Report     │
│  GitHub       │    │  Layout       │    │  Auto-fix    │    │  Dashboard   │
│  GitLab       │    │  Standards    │    │  LLM-assist  │    │  JSON / HTML │
│  HuggingFace  │    │  Health       │    │  PR-ready    │    │  Artifacts   │
└───────────────┘    └───────────────┘    └───────────────┘    └───────────────┘
```

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔍 **Multi-platform Discovery** | Scan GitHub orgs/users, GitLab groups, and Hugging Face namespaces |
| 🧰 **Automated Repair** | Fix missing Makefiles, pyproject.toml, health tests, and HF metadata |
| 🤖 **LLM-Assisted Healing** | OllaBridge Cloud integration for intelligent repair suggestions |
| 🛡️ **Policy Engine** | Risk assessment and change governance before any modifications |
| 📈 **Health Dashboard** | Static JSON + HTML status site deployed to GitHub Pages |
| 🔄 **Self-Healing Loop** | Iterative verify → fix → verify cycle with configurable retry |
| 🔀 **GitPilot Integration** | AI-assisted code repair through the GitPilot agent |
| 📦 **MatrixLab Sandbox** | Isolated execution environment for safe verification |
| 🌐 **GitLab Support** | Full GitLab API v4 integration (gitlab.com + self-hosted) |
| 🤗 **HuggingFace Support** | Model, dataset, and Space repository management |

---



## 🚀 Quick Start

### What SelfRepair Repo does

- clones and inspects a target repository
- checks delivery-readiness signals such as `Makefile`, `pyproject.toml`, tests, install, and start flows
- classifies delivery, security, and compliance issues
- uses AI-assisted repair generation to propose safe fixes
- validates the repaired repository
- returns an audit-friendly final report for enterprise review

### Local backend run

### Installation

```bash
# Clone the repository
git clone https://github.com/ruslanmv/SelfRepair-Repo.git
cd SelfRepair-Repo

# Create virtual environment and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
pip install fastapi uvicorn
```

Or with `uv` (recommended):

```bash
uv sync
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your tokens and settings
```

### Run

```bash
# Start the API backend
uvicorn backend.app.main:app --reload

# Or use the CLI engine
selfrepair-repo discover
selfrepair-repo run
selfrepair-repo check-repo owner/repo-name
selfrepair-repo publish-site
```

---

## 🌍 Open Source Vision

SelfRepair Repo is intended to be a practical, public, and community-driven open-source product for repository quality, delivery readiness, and safe automated repair.

The vision is to make repository maintenance easier for:
- individual developers maintaining side projects
- startup teams that need fast release confidence
- platform teams managing many repositories
- open-source maintainers who need repeatable health checks and repair suggestions

Core principles:
- **Open by default** — normal Git-based workflows, transparent rules, readable reports
- **Safe automation** — validation before and after repair, with auditable changes
- **Vendor-neutral architecture** — usable with common Git platforms, CI systems, and local or hosted AI services
- **Extensible design** — easy to add new analyzers, repair strategies, and policy checks
- **Community contribution** — project rules, templates, and repair strategies should be simple to extend in public



---

## 🔧 Configuration Reference

### Platforms

<details>
<summary><b>🐙 GitHub</b></summary>

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_ORG=my-organization        # or GITHUB_USER=my-username
GITHUB_BASE_BRANCH=main
GITHUB_INCLUDE_PRIVATE=true
```
</details>

<details>
<summary><b>🦊 GitLab</b></summary>

```env
GITLAB_TOKEN=glpat-xxxxxxxxxxxx
GITLAB_URL=https://gitlab.com     # or your self-hosted instance
GITLAB_GROUP=my-group              # or GITLAB_USER=my-username
GITLAB_INCLUDE_PRIVATE=true
```
</details>

<details>
<summary><b>🤗 Hugging Face</b></summary>

```env
HF_TOKEN=hf_xxxxxxxxxxxx
HF_NAMESPACE=my-namespace
HF_REPO_TYPES=model,dataset,space
```
</details>

<details>
<summary><b>🤖 OllaBridge Cloud (LLM Repair)</b></summary>

```env
OLLABRIDGE_ENABLED=true
OLLABRIDGE_BASE_URL=https://your-ollabridge.hf.space
OLLABRIDGE_API_KEY=              # optional
OLLABRIDGE_MODEL=qwen2.5:1.5b
OLLABRIDGE_TIMEOUT=120.0
```

SelfRepair Repo uses OllaBridge's OpenAI-compatible `/v1/chat/completions` endpoint to get LLM-assisted repair suggestions when automated fixes aren't sufficient.
</details>

---

## 🏗️ Architecture

```
selfrepair/
├── cli.py                  # Typer CLI entrypoint
├── main.py                 # Orchestration: discover → check → heal → report
├── settings.py             # Pydantic settings from .env
├── models.py               # Core data models (RepoRef, RepoHealthReport, etc.)
│
├── inventory/              # Repository discovery
│   ├── github_discovery.py  # GitHub org/user scanning
│   ├── gitlab_discovery.py  # GitLab group/user scanning
│   └── huggingface_discovery.py
│
├── analyzers/              # Repository analysis
│   └── repo_analyzer.py     # Layout detection & standard checks
│
├── healing/                # Self-healing engine
│   ├── healing_loop.py      # Iterative verify-fix-verify
│   └── fix_strategies.py    # Safe automated repairs
│
├── llm/                    # LLM integration
│   └── ollabridge_client.py # OllaBridge Cloud API client
│
├── gitpilot/               # GitPilot AI agent integration
├── matrixlab/              # Sandbox execution
├── governance/             # Policy engine & risk assessment
├── standards/              # Repository standard rules
├── reporting/              # Status & incident reporting
├── site/                   # Static dashboard generator
└── storage/                # State persistence
```

---

## 🤖 OllaBridge Integration

SelfRepair Repo integrates with [OllaBridge Cloud](https://github.com/ruslanmv/ollabridge-cloud) for LLM-powered repair intelligence:

1. **Health Check Fails** → SelfRepair Repo detects broken install/test/start
2. **LLM Analysis** → Sends failure context to OllaBridge `/v1/chat/completions`
3. **Smart Suggestions** → Receives repair recommendations from the LLM
4. **Safe Application** → Applies fixes through the governance policy engine

```python
# OllaBridge is used automatically when enabled
# It provides intelligent repair suggestions beyond template fixes
OLLABRIDGE_ENABLED=true
OLLABRIDGE_BASE_URL=https://your-ollabridge.hf.space
```

---

## 🌐 Platform Compatibility

| Platform | Discovery | Clone | Repair | PR/MR | Status |
|----------|-----------|-------|--------|-------|--------|
| **GitHub** | ✅ Org + User | ✅ HTTPS | ✅ Full | ✅ Pull Request | Stable |
| **GitLab** | ✅ Group + User | ✅ HTTPS | ✅ Full | 🚧 Merge Request | Beta |
| **Hugging Face** | ✅ Namespace | ✅ HTTPS | ✅ Metadata | 🚧 Discussion | Beta |

---

## 📈 Repair Coverage

| Check | Auto-Fix | Description |
|-------|----------|-------------|
| `makefile` | ✅ | Ensures `install`, `test`, `start` targets exist |
| `pyproject` | ✅ | Creates/updates pyproject.toml with Python 3.11+ |
| `health_test` | ✅ | Generates `tests/test_health.py` |
| `python311` | ✅ | Enforces `requires-python >= 3.11` |
| `uv` | ✅ | Adds `[tool.uv]` section |
| `readme` | ✅ | Validates README and HF front matter |
| **LLM-assisted** | 🤖 | OllaBridge-powered intelligent fixes |

---

## 🚀 Deployment

### GitHub Actions (Recommended)

SelfRepair Repo ships with ready-to-use workflows:

- **`daily-maintenance.yml`** — Runs health checks daily at 05:15 UTC
- **`manual-run.yml`** — On-demand single repo or full fleet check
- **`publish-status-site.yml`** — Deploys dashboard to GitHub Pages

### HuggingFace Spaces

See [`deploy/huggingface/`](deploy/huggingface/) for Docker-based HF Spaces deployment.

### Docker

```bash
docker build -t selfrepair-repo .
docker run --env-file .env -p 8000:8000 selfrepair-repo
docker compose up --build
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Unit tests only
pytest tests/unit -q

# With coverage
pytest --cov=selfrepair --cov-report=html
```

---

## 📚 Related Projects

| Project | Description |
|---------|-------------|
| [OllaBridge Cloud](https://github.com/ruslanmv/ollabridge-cloud) | Enterprise AI gateway with OpenAI-compatible API |
| [OllaBridge](https://github.com/ruslanmv/ollabridge) | Local AI bridge for Ollama |
| [GitPilot](https://github.com/ruslanmv/gitpilot) | Multi-LLM AI assistant for Git workflows |
| [MatrixLab](https://github.com/agent-matrix/matrixlab) | Sandbox execution environment |

---

## 📄 License

Apache-2.0 © [Ruslan Magana Vsevolodovna](https://github.com/ruslanmv)

---

<p align="center">
  <img src="assets/logo.svg" alt="SelfRepair Repo" width="64" /><br/>
  <sub>Built with ❤️ for the open-source community</sub>
</p>
