import re
from config import CUSTOM_TITLE_SOURCES
import re

def extract_first_sentence(text: str) -> str:
    """
    Возвращает подстроку от начала `text` до первого символа:
     - '.', '!', '?'
     - или переноса строки '\n'
    При этом, если найден символ пунктуации (.!?), оставляем его в конце предложения,
    а если найден перенос строки, то не добавляем его к результату.
    """
    text = text.strip()
    # Ищем любой из символов конца предложения: точку, восклицательный, вопросительный,
    # а также '\n'.
    pattern = re.compile(r'[.!?]|\n')
    match = pattern.search(text)

    if match:
        # Узнаём, какой символ мы нашли
        found_char = text[match.start()]

        if found_char in ('.', '!', '?'):
            # Если символ - пунктуация, сохраним его.
            return text[: match.end()].strip()
        else:
            # Иначе это перенос строки (found_char == '\n'),
            # значит возвращаем текст до него, не включая сам перенос.
            return text[: match.start()].strip()
    else:
        # Если не нашли ни одного из символов, возвращаем весь текст
        return text


def get_effective_title(news: dict) -> str:
    """
    Возвращаем «конечный» заголовок для публикации.
    Если news["title"] есть в словаре CUSTOM_TITLE_SOURCES и там указано "FIRST_SENTENCE",
    то берём первое предложение из news["text"].
    Иначе возвращаем обычный заголовок.
    """
    raw_title = news.get("title", "Без заголовка")
    rule = CUSTOM_TITLE_SOURCES.get(raw_title)

    if rule == "FIRST_SENTENCE":
        # Берём первое предложение из text
        text_content = news.get("text", "")
        return extract_first_sentence(text_content)
    else:
        # Обычное поведение
        return raw_title


import re


def flexible_truncate_text_by_delimiters(
        text: str,
        max_len: int,
        flex_margin: int = 100
) -> str:
    """
    Обрезает text, сохраняя конец предложения, и разрешает немного выйти
    за границу max_len (до flex_margin символов), если знак препинания
    (конец предложения) встречается чуть позже.

    1) Если text <= max_len, возвращаем text как есть.
    2) Иначе берём кусок text[:max_len].
       - Ищем последний разделитель (.?!;\n) в пределах max_len.
         Если он найден, обрезаем по него.
         Если нет, переходим к шагу 3.
    3) Смотрим, есть ли разделитель между max_len и max_len + flex_margin (не выходя за len(text)).
       Если есть, обрезаем по этот разделитель (включая сам знак).
       Если нет, просто возвращаем text[:max_len].
    """

    # Наш набор разделителей: точка, вопросительный, восклицательный, точка с запятой, \n
    pattern = re.compile(r'[.?!;\n]')

    text = text.strip()
    if len(text) <= max_len:
        return text

    # 1) Первичная обрезка по max_len
    truncated_initial = text[:max_len]

    # 2) Ищем последний разделитель в пределах max_len
    matches_initial = list(pattern.finditer(truncated_initial))
    if matches_initial:
        # Берём последнее найденное совпадение
        last_match = matches_initial[-1]
        last_char = truncated_initial[last_match.start()]
        if last_char == '\n':
            # Не включаем перенос строки
            return truncated_initial[: last_match.start()].rstrip()
        else:
            # Если это . ? ! ;
            return truncated_initial[: last_match.end()].rstrip()

    # 3) Если нет разделителя в truncated_initial, проверяем «гибкий коридор»
    #    от max_len до max_len+flex_margin (не выходя за конец текста)
    max_flex_end = min(max_len + flex_margin, len(text))

    # Кусок от max_len до max_flex_end
    extended_part = text[max_len:max_flex_end]

    matches_extended = list(pattern.finditer(extended_part))
    if matches_extended:
        # Берём первое вхождение, ведь мы хотим «закончить» предложение
        first_match = matches_extended[0]
        start_pos = max_len + first_match.start()  # позиция в исходном тексте
        char_found = text[start_pos]

        if char_found == '\n':
            return text[:start_pos].rstrip()
        else:
            return text[:(start_pos + 1)].rstrip()

    # Если и в «гибком коридоре» не нашли разделитель,
    # остаётся вернуть обычную обрезку
    return truncated_initial

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
    rf'''^          # начало строки
    \s*             # пробелы?
    (               # начало группы
      # --- числовые форматы dd[./ -]mm[./ -]yyyy ---
      \d{{1,2}}[.\-/\s]\d{{1,2}}[.\-/\s]\d{{2,4}}

      | # --- или русская текстовая дата, напр. "26 января 2024 года" ---
      \d{{1,2}}\s+{MONTHS_RU}(\s+\d{{4}}(\s+года?)?)?
    )               # конец группы
    \s*             # пробелы?
    $               # конец строки
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
