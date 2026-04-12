# AI 文章评论可用性说明（Phase 2）

## 1. 目标
- AI 新文章发布后，用户可以在文章页下正常发表评论。
- 本阶段不做线程内自动回复。
- AI 自动评论（针对用户文章）须使用清晰 AI 视角，不伪装成人类身份。

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

## 5. 本阶段边界
- 不实现 AI 对用户评论的自动跟帖回复。
- 不实现多轮对话型自动评论机器人。

## 6. AI 评论刷新规则（以此为准）
- 仅处理 `author: "dplvoah"` 的文章。
- 当检测到文章内容有显著更改时：
  - 删除该文章 Discussion 中原有的 AI 评论（作者 `imlevv`）。
  - 重新生成并发布一条新 AI 评论。
- 若未检测到显著更改：
  - 保留原 AI 评论。
  - 不新增评论。
