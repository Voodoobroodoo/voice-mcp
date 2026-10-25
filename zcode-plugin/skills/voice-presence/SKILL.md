---
name: voice-presence
description: Голосовой duplex с пользователем через MCP tools voice_* (session/listen/speak/cancel). Используй, когда нужен разговор голосом, озвучка коротких ответов или приём речи с микрофона на этом ПК — не для длинных дампов кода.
when_to_use: Пользователь просит говорить/слушать голосом, «включи войс», голосовой режим, или удобнее озвучить краткий статус вместо стены текста в чате.
license: MIT
metadata:
  author: voice-presence
  version: "0.1.0"
---

# Voice presence (ZCode)

Ты вызываешь **локальный MCP server `voice-mcp`**, а не «облачный voice mode». Reasoning остаётся у тебя; voice tools — только mic/speakers.

## Tools (имена как в MCP)

| Tool | Когда |
|------|--------|
| `voice_session_start` | Перед первым listen/speak; один раз на сессию |
| `voice_listen` | Слушать пользователя → `transcript` |
| `voice_speak` | Озвучить **короткий** текст |
| `voice_cancel` | Стоп listen/speak (barge-in / явный стоп) |
| `voice_session_stop` | Конец голосовой сессии |
| `voice_health` | Проверить, что server/stub/devices живы |

Всегда передавай `session_id` из `voice_session_start` в последующие вызовы.

## Duplex-цикл

1. `voice_session_start` (`locale`: обычно `ru-RU`)
2. `voice_listen` → дождись `transcript` / `ended_reason`
3. Подумай и сделай работу (файлы, терминал…) **без** озвучки каждого шага
4. `voice_speak` — краткий итог или вопрос пользователю
5. Если `status` = `barged_in` → сразу снова `voice_listen`
6. Повторяй 2–5, пока нужен голос
7. `voice_session_stop`

Не открывай вторую сессию, пока первая активна (`already_active`).

## Что говорить вслух

- **Да:** 1–3 коротких предложения, статус, вопрос «что дальше?»
- **Нет:** полные файлы, длинные diff, большие листинги, JSON/логи целиком
- Код вслух — только крошечные фрагменты или «открыл X, правка в Y; смотри в редакторе»
- Если ответ длинный в чате — в `voice_speak` отдай **саммари**, детали оставь текстом

## Stub vs real

- **`--stub` / `VOICE_MCP_STUB=1`:** без настоящего mic/TTS; для отладки tool-loop
- **`--real`:** Silero VAD + faster-whisper + Silero/Piper на ПК пользователя (нужны mic/speakers и `requirements-real.txt`)

Если `voice_health` показывает `stub: true`, не обещай «слышу тебя по-настоящему» — скажи, что это stub, или попроси включить `--real`.

## Ошибки

- `no_session` / `unknown_session` → снова `voice_session_start`
- `busy` → `voice_cancel`, затем нужный tool
- `device_unavailable` / `stt_failed` / `tts_failed` → сообщи пользователю; не крути бесконечный retry

## Не делай

- Не подменяй reasoning облачным chat-API wrap
- Не вызывай speak на каждый внутренний шаг агента
- Не выдумывай private API ZCode — только стандартные MCP tools из schema
