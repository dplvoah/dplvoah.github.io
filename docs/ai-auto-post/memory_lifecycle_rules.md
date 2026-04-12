# 记忆更新与迁移规则（Phase 4）

## 1. 写入边界（What goes where）
- 可写入 `user_memory`：
  - 重复出现、跨会话稳定、对后续判断有长期影响的用户信息。
- 可写入 `ai_memory`：
  - AI 长期稳定立场、反复验证有效的回应方法、持续思路线索。
- 可写入 `shared_memory`：
  - 已形成共识、已形成核心分歧、重要转折点、长期待追踪问题。
- 仅属于临时上下文（`recent_memory`）：
  - 最近交互摘要、短期焦点、尚未稳定的判断信号、一次性上下文。

## 2. 自动更新策略
- 每次授权身份交互结束后（评论发布 / 回复发布）自动执行：
  - 记录一条 interaction event 到 `ai_context/memory/interaction_events.jsonl`
  - 基于最近事件重建 `ai_context/recent_memory.md`
- 非授权身份不触发核心记忆更新。

## 3. 迁移到稳定记忆的条件
- 迁移前提（建议全部满足）：
  - 跨多个交互反复出现
  - 对后续生成有明确长期价值
  - 与已有稳定记忆不冲突，或已明确替代关系
- 迁移方向：
  - 用户稳定信号 -> `user_memory`
  - AI 持续立场/方法 -> `ai_memory`
  - 共同结论/分歧 -> `shared_memory`

## 4. 删除规则
- 从 `recent_memory` 删除：
  - 过期短期上下文
  - 噪声事件
  - 已迁移至稳定记忆的重复信息
- 从稳定记忆删除或改写：
  - 被新证据明确推翻
  - 已失效且不再影响后续生成
  - 与新版本核心规则冲突

## 5. 权限规则
- 身份权限配置文件：`ai_context/memory_permissions.yaml`
- 当前授权身份：`dplvoah`, `imlevv`
- 未授权身份：
  - `discussion_reply`: `skip`
  - `blog_comment`: `skip`
  - 不得触发 personalized reading/memory writing/memory updating

