# Comments 与 Giscus 运行说明（Phase 4）

## 1. 目标
- 博文页面评论由 Giscus 承载，Discussion 作为后端线程。
- AI 评论与回复用于延续长期思想对话，不做客服式应答。

## 2. 页面映射约束
- 页面组件：`src/components/GiscusComments.astro`
- 映射策略：`pathname`
- canonical key：`blog/<slug>/`
- 每篇文章应最终可解析到唯一 Discussion（优先 `discussionId`，否则按 canonical key 查找/创建）。

## 3. AI 评论规则（文章级）
- 脚本：`scripts/post_ai_comment.py`
- AI 账号：`imlevv`
- 仅当目标身份具备 `personalized_read` 权限时才生成个性化评论。
- 非授权身份遵循 `ai_context/memory_permissions.yaml` 的 `blog_comment` 策略（当前为 `skip`）。

## 4. AI 回复规则（评论级）
- 脚本：`scripts/post_ai_reply_comment.py`
- 触发：`discussion_comment.created`
- 永不回复 AI 自己的评论（作者 `imlevv`）。
- 同一父评论若已有 `imlevv` 回复则跳过。
- 非授权身份遵循 `memory_permissions.yaml` 的 `discussion_reply` 策略（当前为 `skip`）。

## 5. 上下文读取
- 入口：`scripts/build_context.py`
- 策略文件：`ai_context/context_retrieval_policy.yaml`
- 授权身份：读取四层记忆 + 对应 style profile。
- 非授权身份：回退 `generic_<mode>`（仅 generic context + style profile）。

## 6. 运行时记忆刷新
- 授权交互后自动记录事件到：
  - `ai_context/memory/interaction_events.jsonl`
- 并自动重建：
  - `ai_context/recent_memory.md`
- 对应工作流会将上述运行时文件提交回仓库，确保跨运行持久化。

## 7. 相关规范索引
- 回复规范：`docs/ai-auto-post/reply-spec.md`
- 写作规范：`docs/ai-auto-post/writing-spec.md`
- 记忆结构：`docs/ai-auto-post/memory_schema.md`
- 生命周期：`docs/ai-auto-post/memory_lifecycle_rules.md`
- 检索优先级：`docs/ai-auto-post/context-retrieval.md`

