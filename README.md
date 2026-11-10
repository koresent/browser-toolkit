# browser-auditor

Инструмент автоматизированного тестирования, аудита и отладки **UserStyles** (`.user.css`) и **UserScripts** (`.user.js`) на движке **Gecko** с поддержкой профиля браузера **Zen**.

## Основные возможности

1. **Безопасная работа с профилем Zen:**
   - Автоматически находит ваш рабочий профиль Zen (`~/.config/zen/profiles.ini`).
   - Создает мгновенный снимок профиля через CoW reflink (`cp -a --reflink=auto`), сохраняя авторизации, cookies, расширения и локальное хранилище.
   - Очищает блокировки (`lock`, `.parentlock`) и сессионные вкладки, исключая конфликты с запущенным Zen.
   - Гарантированно удаляет временную копию профиля по завершении работы.

2. **Аудит пользовательских стилей (UserStyles):**
   - Парсит метаданные (`==UserStyle==`) и блоки `@-moz-document` (domain, regexp, url, url-prefix).
   - Инжектит стили в DOM и тестирует каждый CSS-селектор на живой странице.
   - Находит «мертвые» селекторы (0 совпадений из-за изменений в верстке сайта) и предлагает кандидатов из DOM на замену.
   - Делает скриншоты страницы «ДО» и «ПОСЛЕ» применения стиля.

3. **Аудит пользовательских скриптов (UserScripts):**
   - Парсит метаданные (`==UserScript==`), `@match`, `@include`, `@run-at`, `@grant`.
   - Внедряет полифиллы для Greasemonkey/Tampermonkey API (`GM_getValue`, `GM_setValue`, `GM_xmlhttpRequest`, `GM_registerMenuCommand` и т.д.).
   - Перехватывает логи консоли, ошибки выполнения и незарегистрированные исключения.
   - Сохраняет скриншот страницы после отработки скрипта.

4. **Инспекция селекторов:**
   - Быстрый просмотр элементов на целевом URL через сессию Zen с выводом классов, атрибутов, вычисленных стилей (`computedStyle`) и HTML-сниппетов.

5. **Режим для ИИ-агентов (`--json`):**
   - Вывод результатов в структурированном JSON для автоматизированного анализа и исправления кода стилей/скриптов.

---

## Установка

Требуются: Python 3.11+, `uv` (или `pip`).

```bash
cd /home/koresent/Projects/personal/browser-auditor
uv venv
uv pip install -e .
```

---

## Использование

### 1. Проверка пользовательского стиля (.user.css)
```bash
# Автоматически определит URL из @-moz-document
uv run browser-auditor audit /path/to/style.user.css

# С переопределением целевого URL:
uv run browser-auditor audit /path/to/style.user.css --url https://github.com/koresent/userstyles

# В формате JSON (для агентов и скриптов):
uv run browser-auditor audit /path/to/style.user.css --json
```

### 2. Проверка пользовательского скрипта (.user.js)
```bash
uv run browser-auditor audit /path/to/script.user.js
```

### 3. Инспекция конкретного селектора на странице
```bash
uv run browser-auditor inspect https://github.com/koresent --selector "div[class*='Copilot']"
```

### 4. Дополнительные флаги
- `--no-profile` — запустить изолированный чистый профиль без использования профиля Zen.
- `--headful` — запустить браузер в графическом режиме с видимым окном.
- `--output <dir>` — директория для сохранения скриншотов и отчетов (по умолчанию `./audit-results/<name>/`).
- `--profile <path>` — путь к конкретному профилю.
