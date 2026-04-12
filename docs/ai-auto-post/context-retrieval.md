# 生成时上下文检索优先级（Phase 4）

## 1. 配置入口
- 配置文件：`ai_context/context_retrieval_policy.yaml`
- 构建器：`scripts/build_context.py`

## 2. 检索顺序（统一规则）
1. 先读 `common_always_on`
2. 再读 `<mode>.always_on`
3. 最后读 `<mode>.optional`（如开启 optional）

## 3. 长度与裁剪
- 每个文件受 `max_chars` 限制（无专门配置时用 `defaults.max_chars_per_file`）。
- 整体受 `<mode>.max_total_chars`（或默认总上限）限制。
- 超限时按读取顺序裁剪，保证高优先级文件优先保留。

## 4. always-on 与 optional 语义
- `always_on`：
  - 缺失或为空时，构建失败（fail fast）。
  - 用于关键身份、记忆、风格约束。
- `optional`：
  - 缺失可跳过。
  - 用于可选增强上下文（如简报文件）。

## 5. 模式映射（当前实现）
- `comment`：用于整篇文章评论生成。
- `reply`：用于单条评论回复生成。
- `reflection`：用于 AI 长文/反思类生成。
- `challenge`、`bridge`：已配置，可在后续流程启用。

## 6. 身份门控
- 如果目标身份有 `personalized_read` 权限：
  - 读取请求 mode（如 `reply`）。
- 如果无权限：
  - 回退到 `generic_<mode>` 或 `generic`（若存在）。
  - 未授权行为最终是否执行由 `memory_permissions.yaml` 决定。

