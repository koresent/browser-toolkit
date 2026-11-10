# browser-toolkit

Комплексный инструментарий автоматизированного тестирования, аудита и **создания Gruvbox-тем** (`.user.css`) и **UserScripts** (`.user.js`) на движке **Gecko** с поддержкой профиля браузера **Zen**.

---

## 🛠️ Инструменты для создания новых Gruvbox-тем

Инструментарий полностью заточен под создание фирменных тем **Gruvbox** (Dark, Dark-Hard, Dark-Soft, Light) в точном соответствии со стилем каталога:

### 1. Реверс-инжиниринг цветов сайта (`extract-palette`)
Сканирует целевой сайт на наличие нативных CSS-переменных (`--color-...`, `--bg-...`) и кластеризует реальные цвета поверхностей, текста и рамок:
```bash
uv run browser-toolkit extract-palette https://habr.com
```

### 2. Семантическое картирование ролей DOM (`map-roles`)
Автоматически группирует селекторы страницы по их функциональным ролям:
- **Базовые поверхности:** холст, тело сайта, основные контейнеры (`var(--bg0)`).
- **Приподнятые поверхности:** шапки, меню, сайдбары (`var(--bg-dark)`).
- **Всплывающие элементы:** карточки, модалки, дропдауны (`var(--bg1)` / `var(--bg2)`).
- **Типографика:** заголовки (`var(--fg0)`), основной текст (`var(--fg1)`), мета/даты (`var(--fg-muted)`), ссылки (`var(--blue)` / hover `var(--yellow)`).
- **Формы:** инпуты, кнопки, чекбоксы (`var(--bg1)`, `var(--bg3)`).
- **Код и иконки:** блоки `pre`/`code`, SVG-фильтры (`filter: sepia(1)`).

```bash
uv run browser-toolkit map-roles https://habr.com
```

### 3. Автоматическая генерация заготовки темы (`scaffold`)
Создает полностью структурированный файл `.user.css` с метаданными UserStyle, переменными Gruvbox и готовыми блоками селекторов под целевой сайт:
```bash
# Сгенерировать тему Gruvbox Dark и сохранить в файл:
uv run browser-toolkit scaffold https://habr.com --name Habr --output habr/gruvbox.user.css

# С вариантом Gruvbox Dark Hard:
uv run browser-toolkit scaffold https://habr.com --variant dark-hard --output habr/gruvbox.user.css
```

### 4. Аудит контрастности по WCAG 2.1 (`check-contrast`)
Проверяет читаемость текста при наложении темы. Рассчитывает относительную яркость и контраст для каждого видимого текста, отслеживая проблемные места (порог 4.5:1 для обычного текста, 3:1 для крупного):
```bash
uv run browser-toolkit check-contrast https://qna.habr.com --css path/to/gruvbox.user.css
```

### 5. Живой предпросмотр с Hot-Reload (`preview`)
Запускает браузер и отслеживает изменения в файле темы. При сохранении файла стили в браузере обновляются на лету за < 50мс без перезагрузки страницы и без потери фокуса:
```bash
# В видимом окне Zen Browser:
uv run browser-toolkit preview https://habr.com habr/gruvbox.user.css

# В фоне со скриншотом при каждом сохранении:
uv run browser-toolkit preview https://habr.com habr/gruvbox.user.css --headless
```

---

## 🔍 Инструменты аудита и багфикса

### 1. Картографирование макетов сайта (`map-site`)
Использует DOM Structural Fingerprinting (сходство Жаккара) для поиска уникальных типов страниц и отсечения повторяющихся однотипных постов:
```bash
uv run browser-toolkit map-site https://qna.habr.com --css path/to/gruvbox.user.css --max-archetypes 5
```

### 2. Пакетный аудит каталогов (`scan`)
```bash
uv run browser-toolkit scan /path/to/userstyles/ --only-broken
```

### 3. Аудит одного стиля или скрипта (`audit`)
```bash
# С глубокой охотой по уникальным архетипам до победного:
uv run browser-toolkit audit path/to/gruvbox.user.css --deep-hunt
```

### 4. Поиск элементов и синтез селекторов (`search`)
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
