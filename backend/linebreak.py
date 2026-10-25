"""Word-aware line breaking for text rendered by handright.

handright wraps text one glyph at a time (``handright/_core.py`` checks the
pen position before every glyph), so it happily splits an English word across
two lines. It also lets a closing punctuation mark start a new line when the
mark is not in its ``end_chars`` set.

The functions here pre-compute the line breaks and insert explicit newlines,
which handright treats as hard line ends. Only space-delimited runs are
affected: a paragraph without spaces is returned untouched, so pure CJK text
keeps handright's own (and therefore unchanged) wrapping.
"""

import unicodedata

# Closing punctuation that must not be pushed to the start of a line.
# Mirrors handright's default ``end_chars``.
CLOSING_PUNCTUATION = "，。》？；：’”】｝、！％）,.>?;:]}!%)′″℃℉"

_SPACES = " \t"


def is_wide(char):
    """True for characters that are laid out one per cell (CJK and friends)."""
    return unicodedata.east_asian_width(char) in ("W", "F")


def _tokenize(paragraph, advance):
    """Split a paragraph into (kind, text, width) units.

    Wide characters are single-character units, runs of narrow (Latin, digit,
    symbol) characters are whole words, and runs of spaces are their own units.
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
    """True when the paragraph is space-delimited.

    Without a space there is nothing to keep together, so the paragraph is left
    to handright and Chinese text keeps exactly the line breaks it had before.
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
                # A space produced by a break is consumed by the break itself;
                # indentation at the start of a line is kept.
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
            # A word has to fit as a whole; only an over-long word is broken.
            if x + width <= max_width - word_margin:
                current.append((kind, text))
                x += width
                continue
            if current:
                # Closing punctuation must not start a line, so keep it on the
                # current line even though it then hangs past the margin.
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
                # Same rule handright uses for a single glyph: it is placed
                # while the pen position is still inside the usable width.
                if current and x > max_width:
                    start_new_line()
                current.append(("char", char))
                x += advance(char)
            continue

        # Wide character: break before it, unless it is closing punctuation
        # that may hang past the right margin instead of starting a line.
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
    """Insert explicit newlines into ``text``.

    ``advance(char)`` returns the pen advance of a glyph, ``max_width`` is the
    usable width (page width minus margins and one nominal font-size cell, the
    same limit handright uses). ``word_margin`` reserves extra room when
    deciding whether a word fits, for callers that perturb glyph spacing.
    """
    if max_width <= 0:
        return text
    return "\n".join(
        _wrap_paragraph(paragraph, advance, max_width, end_chars, word_margin)
        for paragraph in text.split("\n")
    )
