# browser-toolkit

Комплексный инструментарий автоматизированного тестирования, аудита, **создания Gruvbox-тем** (`.user.css`) и **модернизации устаревшей верстки сайтов под стандарты 2026 года** с поддержкой профиля браузера **Zen**.

---

## 🎨 Создание новых тем Gruvbox и редизайн под 2026 год

### 1. Извлечение скелета хардкодных цветов (`extract-colors`)
*Адаптированная и улучшенная версия `Extract-ThemeColors-Universal.ps1` на Python:*
- Принимает **локальный `.css` файл** ИЛИ **URL живого сайта** (автоматически выгружает все подключенные таблицы стилей).
- Отсекает вызовы `var(...)` (как вторичные использования), отбрасывает отступы, сетки и анимации.
- Сохраняет только селекторы с явными хардкодными цветами (HEX, RGB, HSL, named colors) и свойствами фона/рамок/текста:
```bash
# Для локального файла:
uv run browser-toolkit extract-colors /path/to/stylesheet.css --output colors.css

# Напрямую для живого сайта:
uv run browser-toolkit extract-colors https://vikunja.io --output vikunja-colors.css
```

### 2. Аудит устаревшей верстки и эргономики (`audit-layout`)
Находит пережитки верстки 90-х и 2000-х годов:
- Устаревшие шрифты (`Times New Roman`, `Verdana`, `Courier`).
- Сжатый текст (`font-size < 14px` или `line-height < 1.35`).
- Непомерная ширина строк (текстовые блоки шире 950px, утомляющие глаза на 2K/4K).
- Фиксированные неадаптивные контейнеры (`width: 1000px`).
- Табличную верстку:
```bash
uv run browser-toolkit audit-layout https://www.opennet.ru
```

### 3. Автогенерация современной Gruvbox-темы (`scaffold`)
Создает заготовку `.user.css` с переменными Gruvbox, переопределением нативных переменных сайта и **блоком современных улучшений 2026 года**:
- Сглаженная системная типографика (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif`).
- Оптимальная ширина чтения (`max-width: 80ch !important`).
- Тонкие аккуратные скроллбары (`scrollbar-width: thin`).
- Современные скругленные контролы форм с кольцами фокуса доступности (`outline: 2px solid var(--accent)`).
- Моноширинный стек для кода (`JetBrains Mono`, `Fira Code`).
```bash
# Сгенерировать современную Gruvbox тему:
uv run browser-toolkit scaffold https://opennet.ru --name OpenNet --output opennet/gruvbox.user.css

# Без инъекции современных улучшений (только цвета):
uv run browser-toolkit scaffold https://opennet.ru --no-modernize
```

### 4. Реверс-инжиниринг цветов и переменных (`extract-palette`)
```bash
uv run browser-toolkit extract-palette https://habr.com
```

### 5. Семантическая разметка ролей DOM (`map-roles`)
```bash
uv run browser-toolkit map-roles https://habr.com
```

### 6. Проверка контрастности по WCAG 2.1 (`check-contrast`)
```bash
uv run browser-toolkit check-contrast https://qna.habr.com --css path/to/gruvbox.user.css
```

### 7. Живой предпросмотр с Hot-Reload (`preview`)
Мгновенное обновление CSS в открытом Zen Browser без перезагрузки вкладки при каждом сохранении файла:
```bash
uv run browser-toolkit preview https://habr.com /path/to/gruvbox.user.css
```

---

## 🔍 Аудит, поиск и пакетное тестирование

### 1. Картографирование макетов сайта (`map-site`)
DOM Structural Fingerprinting (сходство Жаккара): отличает уникальные типы страниц и отсекает повторяющиеся однотипные посты:
```bash
uv run browser-toolkit map-site https://qna.habr.com --css path/to/gruvbox.user.css --max-archetypes 5
```

### 2. Пакетный аудит каталогов (`scan`)
```bash
uv run browser-toolkit scan /path/to/userstyles/ --only-broken
```

### 3. Аудит одного стиля или скрипта (`audit`)
```bash
uv run browser-toolkit audit path/to/gruvbox.user.css --deep-hunt
```

### 4. Поиск элементов и генерация устойчивых селекторов (`search`)
```bash
uv run browser-toolkit search https://github.com --keyword "copilot"
```

### 5. Тестирование правила на лету (`test-rule`)
```bash
uv run browser-toolkit test-rule https://github.com --css '.selector { display: none !important; }'
```

### 6. Скриншоты и интерактивные действия (`screenshot`, `interact`)
```bash
uv run browser-toolkit screenshot https://github.com --selector "header" --output header.png
```

---

## Установка

```bash
cd /home/koresent/Projects/personal/browser-toolkit
uv venv
uv pip install -e .
```
Все команды поддерживают флаг `--json` для программной интеграции с агентами.
