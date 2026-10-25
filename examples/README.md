# Examples

- [`zcode-mcp-config.example.json`](./zcode-mcp-config.example.json) — generic MCP config for ZCode (после `pip install -e .`).
- Plugin + skill: [`../zcode-plugin/`](../zcode-plugin/).
- Полный runbook: [`../../docs/pc-runbook.md`](../../docs/pc-runbook.md).

Для real + status hub (GUI attach):

```json
{
  "mcpServers": {
    "voice-mcp": {
      "command": "voice-mcp",
      "args": ["--real", "--status"],
      "env": {
        "VOICE_MCP_STUB": "0",
        "VOICE_MCP_LOCALE": "ru-RU"
      }
    }
  }
}
```

Затем на том же ПК: `voice-mcp-gui --attach`.
