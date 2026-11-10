# browser-auditor

Комплексный инструмент автоматизированного тестирования, аудита и отладки **UserStyles** (`.user.css`) и **UserScripts** (`.user.js`) на движке **Gecko** с поддержкой профиля браузера **Zen**.

---

## Возможности

1. **Безопасная работа с профилем Zen:**
   - Автоматически находит ваш рабочий профиль Zen (`~/.config/zen/profiles.ini`).
   - Создает мгновенный снимок профиля через CoW reflink (`cp -a --reflink=auto`), сохраняя авторизации, cookies, расширения и локальное хранилище.
   - Очищает блокировки (`lock`, `.parentlock`) и сессионные вкладки, исключая конфликты с запущенным Zen.
   - Гарантированно удаляет временную копию профиля по завершении работы.

2. **Пакетный аудит каталогов (`scan`):**
   - Сканирует целые каталоги стилей и скриптов в одном сеансе.
   - Выводит наглядную сводку здоровья стилей (`--only-broken` для фильтрации только проблемных).

3. **Интеллектуальный поиск по DOM и генератор устойчивых селекторов (`search`):**
   - Поиск элементов по тексту, ключевым словам в классах/ID/aria-атрибутах, ролям или тегам.
   - Автоматический синтез устойчивых CSS-селекторов (приоритет `data-testid`, `aria-*`, семантические селекторы вместо нестабильных хэшей CSS Modules).

4. **Тестирование гипотез на лету (`test-rule`):**
   - Примерка CSS-правила на живой странице до изменения файла.
   - Оценка влияния (Impact Analysis): процент площади экрана, количество скрываемых элементов, предотвращение случайного скрытия контента страницы.
   - Автоматические скриншоты «ДО» и «ПОСЛЕ».

5. **Интерактивные действия и скриншоты (`screenshot`, `interact`):**
   - Скриншоты отдельных элементов (`--selector`), всей страницы (`--full-page`) или с наведением мыши (`--hover` для проверки меню и `:hover` состояний).
   - Выполнение цепочки действий пользователя (`click`, `hover`, `fill`, `press`, `wait`, `screenshot`) для тестирования модальных окон, дропдаунов и вкладок.

6. **Аудит пользовательских скриптов (UserScripts):**
   - Внедрение полифиллов Greasemonkey/Tampermonkey API (`GM_getValue`, `GM_setValue`, `GM_xmlhttpRequest`, `GM_registerMenuCommand` и т.д.).
   - Перехват ошибок выполнения и логов консоли.

---

## Установка

```bash
cd /home/koresent/Projects/personal/browser-auditor
uv venv
uv pip install -e .
```

---

## Справочник команд

### 1. Пакетное сканирование (`scan`)
```bash
# Проверить здоровье всех стилей в папке habr:
uv run browser-auditor scan /home/koresent/Projects/personal/userstyles/habr

# Вывести только сломанные файлы:
uv run browser-auditor scan /home/koresent/Projects/personal/userstyles/ --only-broken
```

### 2. Аудит одного стиля или скрипта (`audit`)
```bash
# Аудит UserStyle:
uv run browser-auditor audit /path/to/style.user.css

# Аудит UserScript:
uv run browser-auditor audit /path/to/script.user.js
```

### 3. Поиск элементов и синтез селекторов (`search`)
```bash
# Найти все элементы, связанные с Copilot на GitHub:
uv run browser-auditor search https://github.com --keyword "copilot"

# Найти кнопку по тексту:
uv run browser-auditor search https://github.com --text "Sign out" --role button
```

### 4. Проверка правила на лету (`test-rule`)
```bash
uv run browser-auditor test-rule https://github.com --css 'button[aria-label="Open Copilot…"] { display: none !important; }'
```

### 5. Скриншоты элементов и интерактивных состояний (`screenshot`)
```bash
# Скриншот только шапки сайта:
uv run browser-auditor screenshot https://github.com --selector "header" --output /tmp/header.png

# Скриншот выпадающего меню после наведения:
uv run browser-auditor screenshot https://github.com --hover "#user-menu" --output /tmp/menu.png
```

### 6. Цепочка интерактивных действий (`interact`)
```bash
uv run browser-auditor interact https://github.com --actions '[
  {"action": "click", "selector": "button[aria-label=\\"Open Copilot…\\"]"},
  {"action": "wait", "ms": 1000},
  {"action": "screenshot", "path": "/tmp/copilot_opened.png"}
]'
```

### 7. Инспекция селектора (`inspect`)
```bash
uv run browser-auditor inspect https://github.com --selector "header"
```

Все команды поддерживают флаг `--json` для программной интеграции с агентами.
