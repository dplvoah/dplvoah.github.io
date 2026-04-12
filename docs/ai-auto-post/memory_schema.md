# 四层记忆上下文体系（Phase 4）

## 1. 目标
- 将上下文拆分为可维护的四层结构：`user_memory`、`ai_memory`、`shared_memory`、`interaction_preferences`。
- 明确“记忆内容”与“风格控制”分离：风格由 `ai_context/style_profiles/` 管理，不写入记忆正文。

## 2. 四层定义
- `ai_context/memory/user_memory.md`
  - 仅记录用户稳定画像、长期主题、稳定约束、稳定判断标准。
  - 禁止写入短期情绪波动、一次性表述偏好、临时任务细节。
- `ai_context/memory/ai_memory.md`
  - 仅记录 AI 的持续立场、长期已形成判断、已建立回应方式、在延续的思路线索。
  - 禁止写成“AI 的个人经历”。
- `ai_context/memory/shared_memory.md`
  - 仅记录双方已形成共识、核心分歧、反复出现主题、重要转折点、待追踪问题。
  - 不保存逐条聊天流水。
- `ai_context/memory/interaction_preferences.md`
  - 虽非传统 memory，但调用时与 memory 同级读取，工程上纳入同一上下文系统。

## 3. 临时上下文
- `ai_context/recent_memory.md` 为临时窗口（temporary context），由运行时自动刷新。
- 该文件用于承接“最近若干交互摘要”，不应沉淀为稳定人格/价值判断。

## 4. 风格配置（与记忆分离）
- `ai_context/style_profiles/comment.md`
- `ai_context/style_profiles/reply.md`
- `ai_context/style_profiles/reflection.md`
- `ai_context/style_profiles/challenge.md`
- `ai_context/style_profiles/bridge.md`

风格拆解维度：
- 表达风格（简洁度、抽象度、展开程度）
- 互动姿态（对话者/反思者/异议方/主题推进者）
- 输出模式（comment/reply/reflection/challenge/bridge）

