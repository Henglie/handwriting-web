"""给 handright 渲染的文本做按词断行。

2026-10-25：handright 每次画字前判断笔位，逐字换行（``handright/_core.py``），
英文单词会被拆到两行；闭标点不在它的 ``end_chars`` 里时，还会落到行首。

这里的函数预先算好断行并插入显式换行，handright 会把换行当成硬换行。只处理
带空白的段落：没有空白的段落原样返回，纯中文继续交给 handright 自己换行，
行为不变。
"""

import unicodedata

# 2026-10-25：不能出现在行首的闭标点，与 handright 默认的 ``end_chars`` 一致。
CLOSING_PUNCTUATION = "，。》？；：’”】｝、！％）,.>?;:]}!%)′″℃℉"

_SPACES = " \t"


def is_wide(char):
    """判断是否为按单格排版的宽字符（中文及同类字符）。"""
    return unicodedata.east_asian_width(char) in ("W", "F")


def _tokenize(paragraph, advance):
    """把段落拆成 (类型, 文本, 宽度) 单元。

    宽字符各成一个单元，连续的窄字符（英文、数字、符号）合成整词，连续空格
    也自成一个单元。
    """
    tokens = []
    index = 0
    length = len(paragraph)
    while index < length:
        char = paragraph[index]
        if char in _SPACES:
            end = index
            while end < length and paragraph[end] in _SPACES:
                end += 1
            text = paragraph[index:end]
            tokens.append(("space", text, sum(advance(c) for c in text)))
            index = end
        elif is_wide(char):
            tokens.append(("char", char, advance(char)))
            index += 1
        else:
            end = index
            while (
                end < length
                and paragraph[end] not in _SPACES
                and not is_wide(paragraph[end])
            ):
                end += 1
            text = paragraph[index:end]
            tokens.append(("word", text, sum(advance(c) for c in text)))
            index = end
    return tokens


def _needs_wrapping(paragraph):
    """段落含空白时才需要按词断行。

    没有空白就没有需要保持完整的词，整段交给 handright，中文保持原来的断行。
    """
    return any(char in _SPACES for char in paragraph)


def _wrap_paragraph(paragraph, advance, max_width, end_chars, word_margin):
    if not _needs_wrapping(paragraph):
        return paragraph

    lines = []
    current = []
    x = 0.0
    after_break = False

    def start_new_line():
        nonlocal x, after_break
        while current and current[-1][0] == "space":
            current.pop()
        lines.append("".join(text for _, text in current))
        current.clear()
        x = 0.0
        after_break = True

    for kind, text, width in _tokenize(paragraph, advance):
        if kind == "space":
            if not current:
                # 2026-10-25：断行处产生的空格被断行本身吃掉，行首缩进保留。
                if after_break:
                    continue
                current.append((kind, text))
                x += width
                continue
            if x + width > max_width:
                start_new_line()
                continue
            current.append((kind, text))
            x += width
            continue

        if kind == "word":
            # 2026-10-25：单词必须整体放下，只有超长的单词才逐字拆开。
            if x + width <= max_width - word_margin:
                current.append((kind, text))
                x += width
                continue
            if current:
                # 2026-10-25：闭标点不能落到行首，即使悬挂到右边距外也留在
                # 当前行。
                while text and text[0] in end_chars:
                    char = text[0]
                    current.append(("char", char))
                    x += advance(char)
                    text = text[1:]
                width = sum(advance(c) for c in text)
                if not text:
                    continue
                if x + width <= max_width - word_margin:
                    current.append((kind, text))
                    x += width
                    continue
                start_new_line()
            if width <= max_width - word_margin:
                current.append((kind, text))
                x += width
                continue
            for char in text:
                # 2026-10-25：沿用 handright 对单个字的规则：笔位仍在上限内
                # 时才落字。
                if current and x > max_width:
                    start_new_line()
                current.append(("char", char))
                x += advance(char)
            continue

        # 2026-10-25：宽字符在它前面断行；若它是可以悬挂到右边距外的闭标点，
        # 则不断行，避免落到行首。
        if current and x > max_width and text not in end_chars:
            start_new_line()
        current.append((kind, text))
        x += width

    start_new_line()
    return "\n".join(lines)


def break_lines(
    text,
    advance,
    max_width,
    end_chars=CLOSING_PUNCTUATION,
    word_margin=0.0,
):
    """在 ``text`` 中插入显式换行。

    ``advance(char)`` 返回一个字的笔进宽度，``max_width`` 是可用宽度（页宽减
    去左右边距和一个字宽，与 handright 的上限一致）。``word_margin`` 用于在
    判断单词是否放得下时预留余量，供会扰动字距的调用方使用。
    """
    if max_width <= 0:
        return text
    return "\n".join(
        _wrap_paragraph(paragraph, advance, max_width, end_chars, word_margin)
        for paragraph in text.split("\n")
    )
