# voice-mcp — локальный MCP voice server

Presence layer для **ZCode Agent**: tools `voice_*` + CLI + GUI (A+C).  
**На ПК начни здесь:** [docs/pc-runbook.md](../docs/pc-runbook.md) (локальные указатели: [`docs/`](./docs/)).

Также: [context](../docs/project-context.md) · [vision](../docs/voice-mode-vision.md) · [schema](../docs/mcp-voice-schema.md) · [stack](../docs/stt-tts-stack.md) · [install](../docs/install-checklist.md).

SDK: **FastMCP** (`mcp>=1.9,<2`).

## Install

```bash
cd voice-mcp
python3 -m pip install -e .
# проверяет entrypoint:
voice-mcp --help
# или без PATH:
python3 -m voice_mcp --stub
```

Real engines (на ПК с mic):

```bash
python3 -m pip install -r requirements-real.txt
# + PortAudio — см. docs/install-checklist.md
# CPU torch при необходимости:
python3 -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Dev / tests (нужен **pytest-asyncio** — иначе async-тесты падают):

```bash
python3 -m pip install -e ".[dev]"
pytest -q
```

GUI deps (tray + panel):

```bash
python3 -m pip install -e ".[gui]"
# Linux:   sudo apt install python3-tk gir1.2-ayatanaappindicator3-0.1
# macOS:   python.org build + Tcl/Tk; desktop session
# Windows: python.org installer; не headless service
# Без deps: voice-mcp-gui → понятный exit; smoke_gui_import → SKIP (не crash)
```

## Запуск

| Команда | Что |
|---------|-----|
| `voice-mcp --stub` | MCP stdio (default; headless OK) |
| `voice-mcp --real` | MCP stdio + real VAD/STT/TTS |
| `voice-mcp --status --stub` | MCP + **localhost status hub** для GUI |
| `voice-mcp-gui` / `voice-mcp --gui` | **Tray + compact panel** (A+C), stub demo |
| `voice-mcp-gui --attach` | Только GUI → hub `http://127.0.0.1:8765` |
| `voice-mcp health\|turn\|…` | CLI secondary (тот же SessionManager) |

### GUI architecture (A+C)

GUI — companion для человека, **не** замена MCP для агента.

```
ZCode Agent ──MCP tools──► SessionManager ──publish──► Status hub :8765
Human ──tray/panel────────► Status hub (GET /status, POST /control)
```

- **Tray (A):** всегда; цвет = state (idle/listen/think/speak); меню Open panel / Mute / stub|real / Quit  
- **Panel (C):** по клику — state pill, mic level, last transcript, Mute / PTT / Stop, latency+engines  
- Stub: кнопка **Demo turn** гоняет listen→speak без mic  

Headless VM: модули импортируются (`scripts/smoke_gui_import.py`); полный tray нужен desktop (+ иногда `PYSTRAY_BACKEND=appindicator|xorg`).

### Smoke (без mic)

```bash
python3 scripts/smoke_stub.py
python3 scripts/smoke_session.py
python3 scripts/smoke_gui_import.py
pytest -q
```

Optional real (SKIP без devices / без MODELS):

```bash
python3 scripts/smoke_real_optional.py
VOICE_MCP_REAL_SMOKE_MODELS=1 VOICE_MCP_WHISPER_MODEL=base python3 scripts/smoke_real_optional.py
```

## Stub vs real

| Режим | Engines |
|-------|---------|
| `--stub` / `VOICE_MCP_STUB=1` | Заглушки |
| `--real` / `VOICE_MCP_STUB=0` | Silero VAD ONNX + faster-whisper + Silero TTS (или Piper) + sounddevice |

Модели lazy-load при первом listen/speak (`~/.cache/voice-mcp/`, HF, torch.hub).

## Env

| Var | Default | Смысл |
|-----|---------|--------|
| `VOICE_MCP_STUB` | `1` | stub engines |
| `VOICE_MCP_TTS` | `silero` | `silero` \| `piper` |
| `VOICE_MCP_WHISPER_MODEL` | `small` | whisper size |
| `VOICE_MCP_WHISPER_COMPUTE` | `int8` | ctranslate2 type |
| `VOICE_MCP_LOCALE` | `ru-RU` | locale |
| `VOICE_MCP_PIPER_VOICE` | — | Piper `.onnx` path |
| `VOICE_MCP_PIPER_BIN` | `piper` | Piper binary |
| `VOICE_MCP_STATUS` | — | `1` = status hub with MCP |
| `VOICE_MCP_STATUS_PORT` | `8765` | hub port |
| `PYSTRAY_BACKEND` | auto | `appindicator` / `xorg` / `darwin` / `win32` |

**Лицензия:** Silero TTS RU часто **CC BY-NC** → для коммерции `VOICE_MCP_TTS=piper`.

## ZCode plugin + skill

Каталог [`zcode-plugin/`](./zcode-plugin/) — публичная раскладка ZCode (`.zcode-plugin/plugin.json` + `skills/voice-presence/SKILL.md` + `.mcp.json`).  
Инструкция: [`zcode-plugin/README.md`](./zcode-plugin/README.md).  
MCP example: [`examples/zcode-mcp-config.example.json`](./examples/zcode-mcp-config.example.json).

## Структура

```
src/voice_mcp/
  server.py session.py cli.py presence.py
  gui/          tray + panel (A+C)
  audio/        stub + real engines
zcode-plugin/   skill + plugin manifest
tests/          mic-free pytest
scripts/        smoke_* 
docs/           pointers → ../docs/
```

## Ready for PC (чеклист)

1. `pip install -e ".[dev]"` → `pytest -q` + smoke_stub/session зелёные  
2. `pip install -r requirements-real.txt` + PortAudio + mic permissions  
3. `voice-mcp --real` — первый listen/speak (модели скачаются)  
4. При NC Silero: `VOICE_MCP_TTS=piper` + voice path  
5. `pip install -e ".[gui]"` + tk/tray deps → `voice-mcp-gui`  
6. ZCode MCP из `examples/zcode-mcp-config.example.json` (+ skill из `zcode-plugin/`)  
7. Первый duplex: session → listen → speak (или `voice-mcp turn`)  
8. Полный текст: [../docs/pc-runbook.md](../docs/pc-runbook.md)  

**Нужен рабочий стол:** real mic/speakers, GUI tray, замеры latency, проверка ZCode PATH.  
**GitHub:** позже (по запросу).
