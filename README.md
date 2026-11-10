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

## Установка

```bash
cd /home/koresent/Projects/personal/browser-toolkit
uv venv
uv pip install -e .
```
Все команды поддерживают флаг `--json` для программной интеграции с агентами.
