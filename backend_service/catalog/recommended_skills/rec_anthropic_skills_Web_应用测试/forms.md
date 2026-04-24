# Forms

## Trigger
需要处理与Web 应用测试相关的任务时

## Output Format
操作步骤 / 调试建议

## Standard Steps
1. `scripts/with_server.py` - Manages server lifecycle (supports multiple servers)
2. **Use bundled scripts as black boxes** - To accomplish a task, consider whether one of the scripts available in `scripts/` can help. These scripts handle common, complex workflows reliably without cluttering the context window. Use `--help` to see usage, then invoke directly.
3. Use `sync_playwright()` for synchronous scripts
