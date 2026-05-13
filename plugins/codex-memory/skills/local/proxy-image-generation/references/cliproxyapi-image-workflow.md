# CLIProxyAPI Image Workflow

## 核心思路

把“文本主模型 + `image_generation` 工具”包装成一个更直观的别名模型。

- 代理层负责把别名，例如 `gpt-image-1024x1024`，映射到底层文本模型。
- payload override 负责强制注入：
  - `tool_choice={"type":"image_generation"}`
  - `tools=[{"type":"image_generation","size":"1024x1024","quality":"high","background":"auto"}]`
- 调用方只需选择别名并提供提示词。

## 为什么不要直接把 `gpt-image-*` 放进 `model`

OpenAI 官方图片工具文档强调：Responses API 的 `model` 字段要使用主线文本模型，图片能力通过 `image_generation` 工具开启，而不是把 `gpt-image-*` 直接作为 `model`。

截至 2026-04-22，官方文档示例明确写的是“主线模型，例如 `gpt-4.1`、`gpt-4o` 或 `gpt-5.4`，配合 `image_generation` 工具”。

这也是代理别名方案成立的原因：别名是代理语义，不是 OpenAI 原生模型标识。

## 推荐基线

- 默认优先 `gpt-4.1`：兼容面更稳，适合作为保守默认值。
- 如果你的网关明确支持更高版本，例如 `gpt-5.4`，再通过参数切换。
- 如果你的网关内部暴露了文章中的 `gpt-5.4-mini` 之类私有别名，把它作为 `--base-model` 传给脚本即可，不要写死在技能正文里。

## 推荐尺寸策略

- `1024x1024`：通用默认值。
- `1536x1024`：横图。
- `1024x1536`：竖图。

让别名名和尺寸一一对应，例如：

- `gpt-image-1024x1024`
- `gpt-image-1536x1024`
- `gpt-image-1024x1536`

## `render_proxy_alias.py` 生成的片段结构

脚本会输出适合粘贴进 CLIProxyAPI 的 YAML 片段，包含两部分：

1. `oauth-model-alias`
2. `payload.override-raw`

示意：

```yaml
oauth-model-alias:
  codex:
    - name: gpt-4.1
      alias: gpt-image-1024x1024
      fork: true

payload:
  override-raw:
    - models:
        - name: gpt-image-1024x1024
          protocol: codex
      params:
        tools: '[{"type":"image_generation","size":"1024x1024","quality":"high","background":"auto"}]'
        tool_choice: '{"type":"image_generation"}'
```

## `generate_image_response.py` 用法

```bash
python scripts/generate_image_response.py "一张电影海报风格的海边黄昏场景" \
  --model gpt-4.1 \
  --size 1024x1024 \
  --output poster.png
```

可选环境变量：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_RESPONSES_URL`

优先级：

1. `--endpoint`
2. `OPENAI_RESPONSES_URL`
3. `OPENAI_BASE_URL` 推导出的 `/v1/responses`

## 排错

### 400 invalid model

- 不要把 `gpt-image-*` 直接当作官方 `model`。
- 改用主线文本模型，或者先让代理把别名映射到底层模型。

### 返回里没有 `image_generation_call`

- 检查是否真的注入了 `tools` 和 `tool_choice`。
- 检查网关是否过滤掉了工具字段。
- 改用直接调用脚本绕过 CLI 层验证。

### 透明背景不生效

- 检查模型是否支持 `background=transparent`。
- 某些模型只支持不透明背景或自动背景。

### 仍然失败

- 遵守当前仓库约束：429 退避 20 秒；5xx/超时退避 2 秒且最多重试一次。
- 仍失败时给出离线保守答案，并明确声明“需要真实网络接口进一步验证”。
