---
title: RepoGuardian
emoji: "\U0001f6e1\ufe0f"
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
license: apache-2.0
app_port: 7860
---

# RepoGuardian - Enterprise Repository Health Platform

Autonomous health verification, repair, and governance for your entire repository fleet across GitHub, GitLab, and Hugging Face.

## Features

- **Multi-Platform Discovery** - Scan GitHub orgs, GitLab groups, and HuggingFace namespaces
- **Self-Healing Engine** - LLM-assisted automatic repair of broken configs and tests
- **Policy Engine** - Risk assessment and governance controls
- **Enterprise Web UI** - User authentication, dashboards, and audit logging
- **Health Dashboard** - Real-time repository health monitoring

## Default Credentials

- Username: `admin`
- Password: `guardian2024`

> Change the admin password after first login via Settings.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ADMIN_PASSWORD` | Default admin password |
| `SESSION_SECRET` | Secret for session cookies |
| `GITHUB_TOKEN` | GitHub personal access token |
| `GITHUB_ORG` | GitHub organization to scan |
| `GITHUB_USER` | GitHub user to scan |
| `HF_TOKEN` | Hugging Face access token |
| `HF_NAMESPACE` | Hugging Face namespace to scan |

See [GitHub](https://github.com/ruslanmv/RepoGuardian) for full documentation.
