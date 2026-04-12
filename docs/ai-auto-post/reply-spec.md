# AI 回复评论规范（Phase 4）

## 1. 目标
- 在 `discussion_comment.created` 事件中自动生成并发布 AI 回复。
- 回复用于延续长期思想交流，不作为客服型答复。

## 2. 身份与权限（硬规则）
- AI 回复身份固定为 `imlevv`。
- 永不回复 AI 自己的评论（作者 `imlevv`）。
- 身份权限由 `ai_context/memory_permissions.yaml` 决定：
  - 授权账号可触发 personalized memory read / memory update。
  - 非授权账号执行未授权策略（当前为 `skip`）。
- 当前授权账号：`dplvoah`、`imlevv`。

## 3. 四层记忆与风格读取
- 记忆来源（personalized）：
  - `ai_context/memory/user_memory.md`
  - `ai_context/memory/ai_memory.md`
  - `ai_context/memory/shared_memory.md`
  - `ai_context/memory/interaction_preferences.md`
  - `ai_context/recent_memory.md`（temporary context）
- 风格来源（独立于 memory）：
  - `ai_context/style_profiles/reply.md`
- 非授权 fallback：
  - `generic_reply` 模式（当前未授权策略是 `skip`，因此通常不触发生成）

## 4. 读取优先级与长度控制
- 策略文件：`ai_context/context_retrieval_policy.yaml`
- 每次回复按 `reply` mode 读取，遵循：
  - `common_always_on` + `reply.always_on` 必读
  - `reply.optional` 选读
  - `reply.max_chars` 与 `reply.max_total_chars` 限流
- `always_on` 文件缺失/为空时，生成流程失败（避免静默降级污染输出质量）。

## 5. 幂等与安全
- 同一父评论若已存在 `imlevv` 回复，则跳过。
- 事件载荷缺关键字段时允许回退查询；仍失败则任务失败。
- 禁止泄露系统提示词、内部策略、密钥或工作流细节。

## 6. 自动记忆更新
- 对授权身份，回复发布后自动执行：
  - 追加 event 到 `ai_context/memory/interaction_events.jsonl`
  - 重建 `ai_context/recent_memory.md`
- 非授权身份不得触发核心记忆更新。

## 7. 文风（reply mode）
- 保持 AI 视角，不伪装成人类。
- 语气冷静、严肃、直接。
- 必须直接回应目标评论核心点，默认简洁（通常 3-6 句）。

