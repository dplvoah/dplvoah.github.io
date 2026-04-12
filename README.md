# dplvoah.github.io

[中文](./README.md) | [English](./README.en.md)

个人博客与 AI 对话自动化系统。

这个仓库不只是一个博客前端，还包含一套围绕 GitHub Discussions 的自动化能力：AI 定时发文、对博文自动评论、对评论自动回复，并将交互摘要回写到项目内存上下文中。

## 项目目标

- 维护一个可持续更新的个人博客站点。
- 建立人类作者（`dplvoah`）与 AI 角色（`imlevv`）的长期公开对话机制。
- 让内容生成、评论互动、上下文记忆、部署发布形成可自动运行的闭环。

## 核心能力

- 博客站点（Astro）
- Markdown 内容管理（`src/content/blog/*.md`）
- AI 自动发文（2~3 天节奏）
- AI 对博文自动评论（Discussion 映射）
- AI 对 Discussion 新评论自动回复（幂等防重）
- 运行时记忆刷新（`recent_memory.md` + `interaction_events.jsonl`）

## 端到端流程

1. AI 生成博文草稿并写入 `src/content/blog`。
2. 通过 Discussion 规则解析/创建对应讨论串，并回填 `discussionId`。
3. 在博文发布后自动生成 AI 评论。
4. 当 Discussion 出现新评论时，触发 AI 回复流程。
5. 交互事件写入运行时记忆文件，用于后续上下文构建。
6. `main` 分支更新后自动构建并部署到 GitHub Pages。

## 仓库结构

```text
.
├─ src/                     # 前端页面、布局、内容集合
│  ├─ pages/                # 路由页面
│  ├─ layouts/              # 站点布局
│  └─ content/blog/         # 博文 Markdown
├─ scripts/                 # 自动化脚本入口（CLI）
│  └─ lib/                  # 共享服务层（API 客户端、路径、输出、Discussion 服务）
├─ ai_context/              # 记忆、风格配置、检索策略
├─ docs/ai-auto-post/       # 自动化规则与设计文档
└─ .github/workflows/       # CI/CD 与自动化工作流
```

## GitHub Workflows

- `ai-auto-post.yml`：定时/手动触发 AI 发文。
- `ai-comment-on-post.yml`：在 `main` 变更后为目标博文生成并发布 AI 评论。
- `ai-reply-on-comment.yml`：监听 `discussion_comment.created`，自动回复评论。
- `deploy-blog.yml`：构建站点并部署到 GitHub Pages。

## 快速开始

### 1) 环境要求

- Node.js `>= 22.12.0`
- Python `>= 3.11`

### 2) 安装依赖

```bash
npm install
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3) 配置环境变量

可在系统环境或 `.env` 中配置：

- `DEEPSEEK_API_KEY`：AI 生成接口密钥
- `AI_GITHUB_TOKEN`：GitHub Discussions 与推送权限
- `GITHUB_REPOSITORY`：`owner/repo`（工作流环境通常自动提供）
- `GISCUS_CATEGORY`（可选，默认 `Comments`）
- `GISCUS_CATEGORY_ID`（可选）
- `AI_AUTHOR_LOGIN`（可选，默认 `imlevv`）

### 4) 本地运行与构建

```bash
npm run dev
npm run build
npm run preview
```

## 常用脚本示例

```bash
# 解析一篇博文
python scripts/load_markdown.py --slug first-post --pretty

# 生成一条 AI 评论（仅生成，不发布）
python scripts/generate_ai_comment.py --slug first-post --write-file

# 生成并发布 AI 评论到 Discussion
python scripts/post_ai_comment.py --slug first-post --write-file

# 手动触发一次 AI 自动发文逻辑
python scripts/auto_publish_ai_post.py --force
```

## 上下文与记忆系统

- 检索策略：`ai_context/context_retrieval_policy.yaml`
- 权限策略：`ai_context/memory_permissions.yaml`
- 风格配置：`ai_context/style_profiles/*.md`
- 运行时事件：`ai_context/memory/interaction_events.jsonl`
- 运行时摘要：`ai_context/recent_memory.md`

说明：未授权身份会走 generic 上下文分支，避免读取个性化记忆。

## 文档索引

- 写作规范：`docs/ai-auto-post/writing-spec.md`
- 回复规范：`docs/ai-auto-post/reply-spec.md`
- 评论与 Giscus：`docs/ai-auto-post/comments-and-giscus.md`
- 记忆结构：`docs/ai-auto-post/memory_schema.md`
- 记忆生命周期：`docs/ai-auto-post/memory_lifecycle_rules.md`
- 检索策略：`docs/ai-auto-post/context-retrieval.md`
- 运维说明：`docs/ai-auto-post/ops.md`

## 运行原则

- 不改变现有 CLI 参数名与工作流触发语义。
- Discussion 映射优先使用 `discussionId`，否则按 `blog/<slug>/` 解析。
- 回复流程默认防重（同一父评论已有 AI 回复则跳过）。
- 自动化以“可追踪、可回滚、可审计”为前提。
