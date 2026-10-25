# ZCode plugin: voice-presence

Публичная раскладка [ZCode Plugin](https://zcode.z.ai/en/docs/plugin): skill + MCP declaration.

```
zcode-plugin/
├── .zcode-plugin/plugin.json
├── skills/voice-presence/SKILL.md
├── .mcp.json
└── README.md
```

## Установка

1. Сначала пакет: `pip install -e /ABS/PATH/TO/voice-mcp` (чтобы команда `voice-mcp` была в PATH).
2. В ZCode добавь этот каталог как local plugin (см. docs → Plugin) **или** скопируй skill:  
   `~/.zcode/skills/voice-presence/SKILL.md`.
3. `.mcp.json` запускает `voice-mcp --stub --status` (hub для GUI). Для real поменяй на `--real` и `VOICE_MCP_STUB=0`.
4. Settings → Skills / MCP → Refresh.

Если `voice-mcp` не в PATH у GUI-приложения ZCode — в `.mcp.json` используй:

```json
"command": "python3",
"args": ["-m", "voice_mcp", "--stub", "--status"],
"env": { "PYTHONPATH": "/ABS/PATH/TO/voice-mcp/src", "VOICE_MCP_STUB": "1" }
```

Runbook: [`../../docs/pc-runbook.md`](../../docs/pc-runbook.md).  
GUI companion: `voice-mcp-gui --attach`.
