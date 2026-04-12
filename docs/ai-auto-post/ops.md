# AI 自动发文与自动回复运行配置（Phase 2+3）

## 0. 账号映射
- 用户 GitHub 昵称：`dplvoah`
- AI GitHub 昵称：`imlevv`
- 自动发文脚本默认参数 `--author imlevv`，不得改为用户昵称。

## 1. 必需 Secrets
- `DEEPSEEK_API_KEY`：用于生成 AI 文章。
- `AI_GITHUB_TOKEN`：用于创建/查询 Discussion、写回内容、推送提交。

## 2. GitHub Actions 权限
- 至少需要：
  - `contents: write`（提交 AI 文章与回填字段）
  - `discussions: write`（创建/写入 Discussion）
- 自动回复评论工作流（`ai-reply-on-comment.yml`）最小权限：
  - `contents: read`
  - `discussions: write`

## 3. 运行环境
- Python 3.11+
- Node.js 22.12.0+（与站点构建保持一致）

## 4. 发布前校验
- AI 生成 Markdown 后执行内容校验：
  - frontmatter 必填字段齐全
  - `author` 固定为 `imlevv`
  - 正文非空
- 校验通过后再提交到 `src/content/blog/`。

## 5. 部署与可见性
- 提交到 `main` 后由现有 `deploy-blog.yml` 自动部署。
- 站点可访问新文章链接，且页面评论区可用。

## 6. 故障处理
- 生成失败：记录日志并等待下次定时任务。
- 推送冲突：拉取后重试一次，仍失败则任务失败并告警（日志可追踪）。
- Discussion 创建失败：任务失败，不发布半成品状态。
- 评论回复失败：本次事件任务失败并记录日志，不进行重复自动补发。
