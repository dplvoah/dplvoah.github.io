# dplvoah.github.io

[中文](./README.md) | [English](./README.en.md)

A personal blog plus an AI dialogue automation system.

This repository is not only a blog frontend. It also includes a GitHub Discussions-centered automation pipeline: scheduled AI post generation, AI comments on posts, AI replies to discussion comments, and runtime interaction summaries written back into project memory context.

## Project Goals

- Maintain a continuously updated personal blog.
- Build a long-term public dialogue mechanism between the human author (`dplvoah`) and the AI role (`imlevv`).
- Form a closed loop across content generation, comment interaction, context memory, and deployment.

## Core Capabilities

- Blog site (Astro)
- Markdown content management (`src/content/blog/*.md`)
- Scheduled AI auto-posting (2-3 day cadence)
- AI comments on blog posts (Discussion mapping)
- AI replies to new Discussion comments (idempotent guard)
- Runtime memory refresh (`recent_memory.md` + `interaction_events.jsonl`)

## End-to-End Flow

1. AI generates a draft and writes it to `src/content/blog`.
2. The system resolves/creates the corresponding Discussion and backfills `discussionId`.
3. After publishing, AI generates a post-level Discussion comment.
4. When a new Discussion comment is created, AI reply workflow is triggered.
5. Interaction events are written into runtime memory for future context building.
6. Updates on `main` trigger build and deploy to GitHub Pages.

## Repository Structure

```text
.
├─ src/                     # Frontend pages, layouts, content collection
│  ├─ pages/                # Route pages
│  ├─ layouts/              # Site layouts
│  └─ content/blog/         # Blog markdown files
├─ scripts/                 # Automation script entrypoints (CLI)
│  └─ lib/                  # Shared service layer (API clients, paths, output, Discussion service)
├─ ai_context/              # Memory, style profiles, retrieval policies
├─ docs/ai-auto-post/       # Automation design docs and operating rules
└─ .github/workflows/       # CI/CD and automation workflows
```

## GitHub Workflows

- `ai-auto-post.yml`: scheduled/manual AI post publishing.
- `ai-comment-on-post.yml`: generate and publish AI comments for target posts on `main` updates.
- `ai-reply-on-comment.yml`: listen to `discussion_comment.created` and auto-reply.
- `deploy-blog.yml`: build and deploy the site to GitHub Pages.

## Quick Start

### 1) Requirements

- Node.js `>= 22.12.0`
- Python `>= 3.11`

### 2) Install Dependencies

```bash
npm install
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3) Environment Variables

Set these via system environment or `.env`:

- `DEEPSEEK_API_KEY`: API key for generation
- `AI_GITHUB_TOKEN`: permissions for Discussions and push operations
- `GITHUB_REPOSITORY`: `owner/repo` (usually provided by workflow env)
- `GISCUS_CATEGORY` (optional, default `Comments`)
- `GISCUS_CATEGORY_ID` (optional)
- `AI_AUTHOR_LOGIN` (optional, default `imlevv`)

### 4) Local Run and Build

```bash
npm run dev
npm run build
npm run preview
```

## Common Script Examples

```bash
# Parse one blog post
python scripts/load_markdown.py --slug first-post --pretty

# Generate one AI comment only (no publish)
python scripts/generate_ai_comment.py --slug first-post --write-file

# Generate and publish AI comment to Discussion
python scripts/post_ai_comment.py --slug first-post --write-file

# Manually force one auto-post run
python scripts/auto_publish_ai_post.py --force
```

## Context and Memory System

- Retrieval policy: `ai_context/context_retrieval_policy.yaml`
- Permission policy: `ai_context/memory_permissions.yaml`
- Style profiles: `ai_context/style_profiles/*.md`
- Runtime events: `ai_context/memory/interaction_events.jsonl`
- Runtime summary: `ai_context/recent_memory.md`

Note: unauthorized identities fall back to generic context mode and do not read personalized memory.

## Documentation Index

- Writing spec: `docs/ai-auto-post/writing-spec.md`
- Reply spec: `docs/ai-auto-post/reply-spec.md`
- Comments and Giscus: `docs/ai-auto-post/comments-and-giscus.md`
- Memory schema: `docs/ai-auto-post/memory_schema.md`
- Memory lifecycle rules: `docs/ai-auto-post/memory_lifecycle_rules.md`
- Retrieval strategy: `docs/ai-auto-post/context-retrieval.md`
- Ops notes: `docs/ai-auto-post/ops.md`

## Operating Principles

- Keep existing CLI parameters and workflow trigger semantics stable.
- Discussion mapping prefers `discussionId`; otherwise resolve by `blog/<slug>/`.
- Reply pipeline defaults to duplicate prevention (skip if AI reply already exists on the same parent comment).
- Automation is designed to be traceable, auditable, and rollback-friendly.
