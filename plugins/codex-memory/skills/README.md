# Skills

本目录用于放置与 Codex 外脑系统配套的技能文件。

当前包含随包安装的 upstream curated skills：

- `bundled-skills.json`：来源、固定 commit 和默认安装清单。
- `openai-curated/`：从 `https://github.com/openai/skills` 的 `skills/.curated` 固定提取的技能文件。

安装器默认把清单中的技能复制到 `$CODEX_HOME/skills/<skill-name>`。如果目标目录已存在，会跳过并保留用户已有版本；可用 `--skip-skills` 跳过该步骤。
