# browser-toolkit

Инструментарий автоматизации, инспекции, тестирования и создания тем оформления на движке **Gecko** с поддержкой сессий и профиля браузера **Zen**.

Инструмент не пытается вслепую генерировать готовый CSS по шаблонам — вместо этого он предоставляет ИИ-агенту точные «глаза», «руки» и аналитику для создания и доработки качественных тем на основе контекста, структуры и скриншотов конкретного сайта.

---

## 🛠️ Справочник инструментов

### 1. Исследование и сбор данных о сайте
- **`extract-colors <file|url>`**: (Порт и развитие `Extract-ThemeColors-Universal.ps1`)  
  Выгружает CSS-файл или анализирует все таблицы стилей живого сайта, отсекает вызовы `var(...)`, сетки и отступы, оставляя чистый скелет селекторов и хардкодных цветов.
  ```bash
  uv run browser-toolkit extract-colors https://vikunja.io --output vikunja-colors.css
  ```
- **`extract-palette <url>`**:  
  Сканирует сайт на наличие нативных CSS-переменных (`--color-...`, `--bg-...`) и кластеризует реальные цвета фона, текста и рамок по частоте их использования.
  ```bash
  uv run browser-toolkit extract-palette https://habr.com
  ```
- **`map-site <url>`**:  
  Алгоритм DOM Structural Fingerprinting (сходство Жаккара). Обходит сайт и находит уникальные типы страниц (лента, карточка статьи, профиль, настройки), отсекая повторяющиеся одинаковые посты форума.
  ```bash
  uv run browser-toolkit map-site https://qna.habr.com --max-archetypes 5
  ```
- **`search <url>`**:  
  Ищет элементы по тексту, ключевым словам или ARIA-ролям и синтезирует устойчивые селекторы (`data-testid`, `aria-*`, стабильные ID) вместо хрупких хэшей CSS Modules.
  ```bash
  uv run browser-toolkit search https://github.com --keyword "copilot"
  ```
- **`inspect <url> --selector <sel>`**:  
  Быстрый просмотр computed-стилей, геометрии и HTML-сниппета элемента.

---

### 2. Разработка, тестирование и живая примерка
- **`test-rule <url> --css <rule>`**:  
  Мгновенная примерка гипотезы до изменения файла темы. Оценивает Impact (сколько элементов затронуто, не скрыто ли случайно более 25% экрана) и снимает пару скриншотов ДО/ПОСЛЕ.
  ```bash
  uv run browser-toolkit test-rule https://github.com --css 'button[aria-label="Open Copilot…"] { display: none !important; }'
  ```
- **`preview <url> <style.user.css>`**:  
  Живой Hot-Reload сервер. Следит за файлом темы на диске и при сохранении мгновенно инжектит обновленный CSS в открытый Zen Browser за < 20 мс без перезагрузки вкладки.
  ```bash
  uv run browser-toolkit preview https://habr.com /path/to/gruvbox.user.css
  ```
- **`screenshot <url>`**:  
  Скриншоты отдельных элементов (`--selector`), всей страницы (`--full-page`) или с наведением мыши (`--hover` для дропдаунов и `:hover`).
- **`interact <url> --actions <json>`**:  
  Выполнение цепочки действий пользователя (`click`, `hover`, `fill`, `wait`, `screenshot`) для проверки модалок, табов и динамических состояний.

---

### 3. Контроль качества и валидация
- **`check-responsive <url> [--css <file>] [--screenshots-dir <dir>]`**:  
  Проверка адаптивности на экранах смартфонов (390x844), планшетов (768x1024) и десктопов (1440x900). Находит:
  - Горизонтальный скролл (layout blowout) с указанием конкретных элементов, ломающих ширину вьюпорта (`overflow: +N px`), их селекторов и стилей (`width`, `max-width`, `overflow-x`);
  - Слишком мелкие тач-таргеты на мобильных устройствах (< 24x24px по WCAG 2.5.8);
  - Обрезание текста (`overflow: hidden` без `text-overflow: ellipsis`);
  - Перекрытие экрана фиксированными шапками/панелями (> 30% экрана);
  - Автоматически сохраняет скриншоты для каждого разрешения при передаче `--screenshots-dir`.
  ```bash
  uv run browser-toolkit check-responsive https://qna.habr.com --css path/to/style.user.css --screenshots-dir ./screenshots
  ```
- **`check-theme <url> [--css <file>] [--theme dark|light]`**:  
  Глубокий аудит визуальных косяков темы:
  - Неперекрашенные белые пятна (white bleedthrough) — карточки, списки и блоки с белым/светлым фоном в темной теме;
  - Сливающийся невидимый текст (контраст < 1.8:1, когда фон перекрашен, а цвет шрифта забыт);
  - Формы и инпуты (`<input>`, `<textarea>`, `<select>`) с белым родным фоном или невидимым цветом ввода;
  - Потерявшиеся SVG-иконки с темным хардкодным `fill`/`stroke` на темном фоне;
  - Проверка стилизации нативного скроллбара (`scrollbar-color`).
  ```bash
  uv run browser-toolkit check-theme https://qna.habr.com --css path/to/gruvbox.user.css
  ```
- **`check-contrast <url> --css <file>`**:  
  Аудит контрастности по стандарту WCAG 2.1 (4.5:1 для обычного текста, 3:1 для крупного). Находит трудночитаемые элементы при наложении темы и выдает точные значения fg/bg.
  ```bash
  uv run browser-toolkit check-contrast https://qna.habr.com --css path/to/gruvbox.user.css
  ```
- **`audit <file> [--deep-hunt]`**:  
  Проверяет актуальность селекторов в `.user.css` или работу `.user.js` (с полифиллами GM API). В режиме `--deep-hunt` обходит сайт по всем уникальным архетипам до победного.
  ```bash
  uv run browser-toolkit audit path/to/gruvbox.user.css --deep-hunt
  ```
- **`scan <dir> [--only-broken]`**:  
  Пакетное сканирование целых каталогов стилей и скриптов в одном сеансе.

---

### 4. Инструментарий для UserScripts (.user.js)
- **`test-script <file> [--url <url>] [--command <cmd>] [--actions <json>]`**:  
  Глубокое тестирование логики скрипта с полным набором полифиллов `GM_*` и современного `GM.*` Promise API (с обходом CSP страницы):
  - **DOM Mutation Tracking**: фиксирует все вставленные/удаленные узлы и измененные атрибуты;
  - **Сетевой перехват**: лог запросов `GM_xmlhttpRequest` (URL, метод, статус, тело, время);
  - **Тестирование команд меню**: вызов любой функции из `GM_registerMenuCommand` через `--command "Имя команды"`;
  - **Буфер обмена и уведомления**: логирование вызовов `GM_setClipboard` и `GM_notification`.
  ```bash
  uv run browser-toolkit test-script /path/to/script.user.js --command "✅ Active Forks"
  ```
- **`check-spa <file> <target-spa-url> [--initial-url <url>]`**:  
  Проверка устойчивости к SPA-навигации (GitHub Turbo, YouTube `yt-navigate-finish`, `popstate`, PJAX). Показывает, сохранились ли созданные скриптом кнопки и не возникло ли ошибок в обработчиках.
  ```bash
  uv run browser-toolkit check-spa /path/to/script.user.js https://github.com/koresent/browser-toolkit
  ```
- **`preview-js <file> [--url <url>]`**:  
  Live Hot-Reload сервер для разработки скриптов. При каждом сохранении `.user.js` моментально перезагружает страницу в Zen Browser и выводит свежий лог мутаций DOM, сети и консоли.
  ```bash
  uv run browser-toolkit preview-js /path/to/script.user.js
  ```

---

### 5. Управление расширениями Stylus и Violentmonkey (`ext`)
Прямое подключение к базам данных SQLite/IndexedDB расширений профиля Zen Browser:
- **`ext status`**:  
  Показывает расположение профиля Zen, пути к базам данных расширений Stylus и Violentmonkey, количество установленных и активных стилей и скриптов.
  ```bash
  uv run browser-toolkit ext status
  ```
- **`ext list-styles [--search <query>]`**:  
  Список всех стилей, установленных в Stylus (статус активности, ID, целевые домены).
  ```bash
  uv run browser-toolkit ext list-styles --search "habr"
  ```
- **`ext list-scripts [--search <query>]`**:  
  Список всех скриптов, установленных в Violentmonkey (статус активности, версия, правила `@match`).
  ```bash
  uv run browser-toolkit ext list-scripts
  ```
- **`ext diff-styles <local_dir>` / `ext diff-scripts <local_dir>`**:  
  Сравнение локальных файлов репозитория (`.user.css` / `.user.js`) с активной базой браузера. Выявляет:
  - Стили и скрипты, которые рассинхронизировались по содержимому (изменены локально или в браузере);
  - Новые локальные файлы, еще не установленные в браузер;
  - Элементы, установленные в браузере, но отсутствующие в git-репозитории.
  ```bash
  uv run browser-toolkit ext diff-styles /home/koresent/Projects/personal/userstyles
  uv run browser-toolkit ext diff-scripts /home/koresent/Projects/personal/userscripts
  ```
- **`ext export-styles <out_dir>` / `ext export-scripts <out_dir>`**:  
  Прямой дамп всей базы Stylus или Violentmonkey в чистые `.user.css` и `.user.js` файлы на диск.
  ```bash
  uv run browser-toolkit ext export-styles ./dump-styles/
  ```
- **`ext backup [--styles-dir <dir>] [--scripts-dir <dir>]`**:  
  Сборка готовых бандлов резервных копий: `stylus-backup.json` (импортируется в Stylus в 1 клик) и `vm-backup.zip` (импортируется в Violentmonkey).
  ```bash
  uv run browser-toolkit ext backup
  ```
- **`ext serve [--port 8080]`**:  
  Локальный хаб и веб-сервер с Gruvbox-дашбордом. Отображает все локальные стили и скрипты с кнопками **1-Click Install**, которые Stylus и Violentmonkey нативно перехватывают при клике в Zen Browser.
  ```bash
  uv run browser-toolkit ext serve --port 8080
  ```

- **Прямое программное управление стилями (Stylus)**:
  - `ext enable-style <ID_или_имя>`: Включить установленный стиль.
  - `ext disable-style <ID_или_имя>`: Выключить мешающий стиль (необходимо агенту при отладке страниц).
  - `ext toggle-style <ID_или_имя>`: Переключить активность стиля на противоположную.
  - `ext delete-style <ID_или_имя>`: Удалить стиль из базы Stylus.
  - `ext install-style <path_to_usercss> [--disabled]`: Установить новый или перезаписать существующий стиль напрямую в SQLite storage Stylus без участия UI браузера.
  ```bash
  uv run browser-toolkit ext disable-style "Discord Gruvbox"
  uv run browser-toolkit ext toggle-style 6
  uv run browser-toolkit ext install-style ./userstyles/habr/habr.user.css
  uv run browser-toolkit ext delete-style "Old Habr Theme"
  ```

- **Прямое программное управление скриптами (Violentmonkey)**:
  - `ext enable-script <ID_или_имя>`: Включить установленный скрипт.
  - `ext disable-script <ID_или_имя>`: Выключить скрипт (для изоляции багов).
  - `ext toggle-script <ID_или_имя>`: Переключить активность скрипта.
  - `ext delete-script <ID_или_имя>`: Удалить скрипт и сопутствующие данные (`code`, `mod`, `val`).
  - `ext install-script <path_to_userjs> [--disabled]`: Установить или обновить `.user.js` напрямую в SQLite storage Violentmonkey.
  ```bash
  uv run browser-toolkit ext disable-script "YouTube Shorts Redirect"
  uv run browser-toolkit ext toggle-script 1
  uv run browser-toolkit ext install-script ./userscripts/anti-adblock.user.js
  uv run browser-toolkit ext delete-script 18
  ```

---

## Установка

```bash
cd /home/koresent/Projects/personal/browser-toolkit
uv venv
uv pip install -e .
```
Все команды поддерживают флаг `--json` для программной интеграции с агентами.
