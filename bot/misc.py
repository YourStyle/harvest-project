import re
from config import CUSTOM_TITLE_SOURCES
from bs4 import BeautifulSoup

TO_REMOVE_PATTERNS = [
    r'^Экспорт/Импорт\s*$',
    r'^Фот\w*:\s*.*',
    r'(?i)^\s*подписывайтесь на нас в\s*$',
    r'(?i)^\s*дзен\s*$',
    r'(?i)^\s*telegram\s*$',
    r'(?i)^\s*и\s*$',
]


def compress_newlines(text: str) -> str:
    """
    Удаляет полностью пустые строки (в том числе состоящие только из пробелов).
    """
    lines = text.split('\n')
    # Берём только те строки, в которых есть не-пробельные символы.
    new_lines = [line for line in lines if line.strip()]
    # Склеиваем обратно.
    return '\n'.join(new_lines).strip()


def join_single_word_lines(text: str) -> str:
    """
    Ищет строки, в которых ровно одно слово (без учёта пробелов в начале/конце),
    и «приклеивает» такие строки к предыдущей, отделяя пробелом.

    При этом:
    - Пустые строки не трогаются и не "склеиваются".
    - Если "одиночное слово" оказалось в самом верху (либо перед ним пустая строка),
      оно остаётся как есть (не получится «приклеить»).
    """
    lines = text.splitlines()
    new_lines = []

    for line in lines:
        stripped_line = line.strip()
        # Проверяем, пустая ли это строка
        if not stripped_line:
            # Просто добавляем пустую строку
            new_lines.append(line)
            continue

        # Если в строке ровно одно слово:
        words = stripped_line.split()
        if len(words) == 1:
            # Есть ли предыдущая непустая строка, к которой можно приклеить?
            if new_lines and new_lines[-1].strip():
                # Удалим лишние пробелы в конце предыдущей и добавим текущее «одиночное слово»
                new_lines[-1] = new_lines[-1].rstrip() + " " + stripped_line
            else:
                # Если пред. строки нет или она пустая — придётся оставить как есть
                new_lines.append(line)
        else:
            new_lines.append(line)

    return "\n".join(new_lines)


def extract_and_remove_first_sentence(text: str):
    """
    Извлекает первое «предложение» (до одного из символов .?!;\n) вместе с этим знаком,
    возвращает кортеж (это_предложение, остаток_текста).
    Если нет разделителей, значит весь text — одно предложение.
    """
    text = text.strip()
    pattern = re.compile(r'[.?!;\n]')
    match = pattern.search(text)

    if not match:
        # Не нашли ни точек, ни восклицательных/вопросительных, ни переноса и т.п. —
        # значит весь текст и есть "одно предложение".
        return text, ""

    # Вырезаем первое предложение, включая найденный знак препинания (кроме \n)
    found_char = text[match.start()]
    if found_char == '\n':
        # Если попался перенос строки, значит предложение заканчивается прямо перед ним
        first_sentence = text[:match.start()].strip()
        remainder = text[match.start() + 1:].lstrip()
    else:
        # Если это ., !, ? или ; — добавим его к предложению
        first_sentence = text[:match.end()].strip()
        remainder = text[match.end():].lstrip()

    return first_sentence, remainder


def extract_first_sentence(text: str) -> str:
    """
        (ИСПОЛЬЗУЕТСЯ ВНУТРИ get_effective_title, если нужно)
        Возвращает подстроку от начала `text` до первого символа .?!\n.
        Сохраняет символ, если это пунктуация, и отбрасывает, если это \n.
    """
    text = text.strip()
    pattern = re.compile(r'[.!?]|\n')
    match = pattern.search(text)

    if match:
        # Узнаём, какой символ мы нашли
        found_char = text[match.start()]

        if found_char in ('.', '!', '?'):
            return text[: match.end()].strip()
        else:
            return text[: match.start()].strip()
    else:
        return text


def get_effective_title(news: dict) -> str:
    """
    Если в CUSTOM_TITLE_SOURCES для данного заголовка прописано "FIRST_SENTENCE",
    то берём первое предложение из news["text"].
    Иначе — обычный заголовок.
    """
    raw_title = news.get("title", "Без заголовка")
    rule = CUSTOM_TITLE_SOURCES.get(raw_title)

    if rule == "FIRST_SENTENCE":
        text_content = news.get("text", "")
        return extract_first_sentence(text_content)
    else:
        return raw_title


def flexible_truncate_text_by_delimiters(
        text: str,
        max_len: int,
        flex_margin: int = 200
) -> str:
    """
    Обрезает text, стараясь завершить на знаках пунктуации (.?!;\n), и разрешает
    чуть выйти за границу max_len (до flex_margin символов). Если во всех этих
    пределах не найден знак, принудительно идём дальше до ближайшего разделителя.
    """

    # Наш набор разделителей: точка, вопросительный, восклицательный, точка с запятой, \n
    pattern = re.compile(r'[.?!;\n]')

    text = text.strip()
    if len(text) <= max_len:
        # 1) Если весь текст короче лимита, возвращаем без изменений
        return text

    # 2) Первичная обрезка по max_len
    truncated_initial = text[:max_len]

    max_flex_end = min(max_len + flex_margin, len(text))
    extended_part = text[max_len:max_flex_end]
    matches_extended = list(pattern.finditer(extended_part))
    if matches_extended:
        first_match = matches_extended[0]
        start_pos = max_len + first_match.start()
        char_found = text[start_pos]
        if char_found == '\n':
            return text[:start_pos].rstrip()
        else:
            return text[: (start_pos + 1)].rstrip()

    # 3) Ищем последний разделитель в пределах max_len
    matches_initial = list(pattern.finditer(truncated_initial))
    if matches_initial:
        last_match = matches_initial[-1]
        last_char = truncated_initial[last_match.start()]
        if last_char == '\n':
            # Не включаем перенос строки
            return truncated_initial[: last_match.start()].rstrip()
        else:
            # Если это . ? ! ;
            return truncated_initial[: last_match.end()].rstrip()



    # 5) Если в гибком коридоре тоже не нашли разделитель,
    rest_part = text[max_flex_end:]
    matches_rest = list(pattern.finditer(rest_part))
    if matches_rest:
        # Берём первое вхождение за пределами гибкого коридора
        forced_match = matches_rest[0]
        forced_start_pos = max_flex_end + forced_match.start()
        char_found = text[forced_start_pos]
        if char_found == '\n':
            return text[:forced_start_pos].rstrip()
        else:
            return text[: (forced_start_pos + 1)].rstrip()


def remove_first_sentence_if_in_title(text: str, title: str) -> str:
    """
    Извлекает из text первое "предложение" (до одного из символов .?!;\n)
    и если оно целиком входит в title (без учёта регистра и лишних пробелов),
    то удаляем это предложение из начала text.
    """

    text = text.strip()
    title_lower = title.strip().lower()

    # Регулярка для поиска первого "предложенческого" разделителя
    pattern = re.compile(r'[.?!;\n]')
    match = pattern.search(text)
    if not match:
        # Если в тексте нет ни точек, ни вопросит./восклицат. знаков и т. п.,
        # тогда всё text - "одно предложение".
        first_sentence = text
        rest_text = ""
    else:
        # Берём часть до найденного символа
        first_sentence = text[:match.end()].strip()
        rest_text = text[match.end():].lstrip()

    # Сравниваем (без учёта регистра) - входит ли первое предложение в title
    # Можно сделать "exact match", если нужно точное совпадение.
    # Для простоты: если первое предложение как подстрока входит в title_lower.
    first_sentence_lower = first_sentence.lower()

    if first_sentence_lower and first_sentence_lower in title_lower:
        # Удаляем это первое предложение (возвращаем 'rest_text')
        return rest_text
    else:
        # Оставляем, как было
        return text


# Месяцы по-русски в родительном падеже
MONTHS_RU = (
    r'(январ[ья]|феврал[я]|марта|апреля|ма[йя]|июн[яья]|июл[яья]|'
    r'августа|сентябр[я]|октябр[я]|ноябр[я]|декабр[я])'
)

# Пример: r'^\s*26 января( \d{4} (года?)?)?\s*$'
# Соединим это в одну большую регулярку:
DATE_REGEX = re.compile(
    rf'''^
    \s*
    (
      \d{{1,2}}[.\-/\s]\d{{1,2}}[.\-/\s]\d{{2,4}}
      |
      \d{{1,2}}\s+{MONTHS_RU}(\s+\d{{4}}(\s+года?)?)?
    )
    \s*
    $
    ''',
    re.VERBOSE | re.IGNORECASE
)


def remove_publication_date_lines(text: str) -> str:
    """
    Удаляем строки, которые (а) выглядят как дата (DATE_REGEX) и
    (б) расположены либо:
       - в начале (первая строка) или конце (последняя строка),
       - или отделены сверху/снизу пустой строкой.
    Возвращаем очищенный текст.
    """

    lines = text.splitlines()
    new_lines = []

    def is_empty_line(ln: str) -> bool:
        return not ln.strip()

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        if not line_stripped:
            # Пустая строка, просто добавим
            new_lines.append(line)
            continue

        # Проверяем, подходит ли под шаблон даты
        if DATE_REGEX.match(line_stripped):
            # Проверим позицию в тексте
            is_first = (i == 0)
            is_last = (i == len(lines) - 1)

            # Проверим наличие пустой строки сверху или снизу
            prev_line_empty = (i > 0 and is_empty_line(lines[i - 1]))
            next_line_empty = (i < len(lines) - 1 and is_empty_line(lines[i + 1]))

            # Условие удаления:
            # 1) первая строка, или
            # 2) последняя строка, или
            # 3) если сверху или снизу пустая строка
            if is_first or is_last or prev_line_empty or next_line_empty:
                # Пропускаем (не добавляем в new_lines)
                continue

        # Если не попали под условие удаления, оставляем строку
        new_lines.append(line)

    # Склеиваем обратно
    return "\n".join(new_lines)


def remove_custom_fragments(text: str) -> str:
    lines = text.splitlines()
    new_lines = []

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        matched_pattern = any(
            re.match(pattern, line_stripped, re.IGNORECASE)
            for pattern in TO_REMOVE_PATTERNS
        )

        if matched_pattern:
            # Проверяем, есть ли пустая строка сверху *или* снизу
            prev_empty = (i > 0 and not lines[i - 1].strip())
            next_empty = (i < len(lines) - 1 and not lines[i + 1].strip())

            if prev_empty or next_empty:
                # Удаляем
                continue

        new_lines.append(line)

    return "\n".join(new_lines)



def clean_news_html(html: str) -> str:
    """
    Извлекает текст только из тегов <div>, <p> и <span>, убирая прочие теги.
    Для этого используется BeautifulSoup. Если его нет, нужно установить:
        pip install beautifulsoup4
    """

    soup = BeautifulSoup(html, 'html.parser')

    # Соберём текст из всех <div>, <p> и <span>, включая их потомков
    extracted_texts = []
    for tag in soup.find_all(['div', 'p', 'span']):
        # get_text() вернёт текст всего вложенного содержимого
        # strip=True убирает пробелы/переносы по краям
        text_chunk = tag.get_text(strip=True)
        if text_chunk:
            extracted_texts.append(text_chunk)

    # Склеим все фрагменты, вставляя перенос строки
    cleaned_text = "\n".join(extracted_texts)
    return cleaned_text
