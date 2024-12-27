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