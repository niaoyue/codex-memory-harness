---
name: proxy-image-generation
description: Configure Codex and CLI-compatible gateways for image generation through the Responses API `image_generation` tool, including CLIProxyAPI alias templates and local save scripts. Use when Codex needs to enable or debug image generation, create proxy-backed image model aliases, inject `tool_choice`/`tools`, or save generated images from a compatible `/v1/responses` endpoint.
---

# Proxy Image Generation

## Quick Start

1. 判断目标是“给 Codex 增加可选生图模型别名”还是“直接验证接口能否出图”。
2. 如果需要代理别名，运行 `scripts/render_proxy_alias.py` 生成 CLIProxyAPI 片段。
3. 如果需要直接出图，运行 `scripts/generate_image_response.py` 调兼容的 `/v1/responses` 端点并保存图片。
4. 如果需要选模型、尺寸或排错，再读取 `references/cliproxyapi-image-workflow.md`。

## Workflow

### 1. 选择模式

- 优先使用“代理别名模式”让 Codex 出现明确的伪模型名，例如 `gpt-image-1024x1024`。
- 仅在快速验通或不想改代理配置时使用“直接调用模式”。
- 不要把 `gpt-image-*` 直接填进 Responses API 的 `model` 字段，除非你的网关自行兼容该写法。

### 2. 生成代理配置

运行：

```bash
python scripts/render_proxy_alias.py --base-model gpt-4.1 --size 1024x1024 --size 1536x1024
```

- 让别名把尺寸编码进名字，避免隐式魔法值。
- 让 `tool_choice` 固定为 `image_generation`。
- 让 `tools` 中的尺寸、质量、背景显式配置，不依赖网关默认值。

### 3. 直接生成图片

运行：

```bash
python scripts/generate_image_response.py "一只赛博朋克风格的机械狐狸站在雨夜街头" --model gpt-4.1 --size 1024x1024 --output output.png
```

- 通过 `OPENAI_API_KEY` 读取密钥。
- 通过 `OPENAI_BASE_URL` 或 `--endpoint` 指向官方或兼容网关。
- 默认把图片写入本地文件，不在终端回显二进制内容。

### 4. 验证与回退

- 先检查输出文件存在且非空。
- 如果返回 429，等待 20 秒后仅重试一次。
- 如果返回 5xx 或超时，等待 2 秒后仅重试一次。
- 如果仍失败，返回保守离线结论，并明确提示当前技能无法替代实际接口验通。

## Guardrails

- 只通过环境变量传递密钥，不把密钥写入脚本、配置、提交记录或日志。
- 优先使用官方支持的主模型，再按网关实际支持情况替换。
- 让所有尺寸、质量、背景、输出路径通过参数显式传入，不写死到代码外的隐藏位置。
- 修改代理配置前先读取现有文件并只追加必要片段，不覆盖无关配置。

## Resources

- 使用 `references/cliproxyapi-image-workflow.md` 选择基线模型、尺寸策略与排错路径。
- 使用 `scripts/render_proxy_alias.py` 生成 CLIProxyAPI 别名与 payload override 片段。
- 使用 `scripts/generate_image_response.py` 直接调用兼容的 Responses API 并把图片落盘。
