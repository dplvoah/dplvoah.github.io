# AI 文章评论可用性说明（Phase 2+3）

## 1. 目标
- AI 新文章发布后，用户可以在文章页下正常发表评论。
- AI 自动评论（针对用户文章）须使用清晰 AI 视角，不伪装成人类身份。
- AI 自动回复（针对目标用户评论）须使用清晰 AI 视角，不伪装成人类身份。

## 2. 页面侧要求
- 博文页使用 `GiscusComments.astro`。
- `giscus` 的映射策略保持 `pathname`，确保 `/blog/<slug>/` 对应固定讨论线程。

## 3. Discussion 侧要求
- 每篇 AI 文章需要可解析到对应 Discussion：
  - 若 frontmatter 有 `discussionId`，直接使用。
  - 若无 `discussionId`，按 canonical key（`blog/<slug>/`）查找或自动创建。
  - 创建/解析后回填 `discussionId` 到文章 frontmatter。

## 4. 可评论的判定
- 文章页面已加载 giscus 组件。
- 页面可见讨论区输入框。
- 用户提交评论后，评论出现在对应 Discussion 线程。

## 5. 回复规则（Phase 3）
- AI 回复必须以 `imlevv` 账号发布。
- 永不回复 AI 自己的评论（作者 `imlevv`）。
- 对 `dplvoah` 的评论，100% 回复。
- 暂不开放对其他用户评论的自动回复。
- 同一父评论若已存在 `imlevv` 回复，本轮跳过，避免重复回复。

## 6. AI 评论刷新规则（以此为准）
- 仅处理 `author: "dplvoah"` 的文章。
- 当检测到文章内容有显著更改时：
  - 删除该文章 Discussion 中原有的 AI 评论（作者 `imlevv`）。
  - 重新生成并发布一条新 AI 评论。
- 若未检测到显著更改：
  - 保留原 AI 评论。
  - 不新增评论。
