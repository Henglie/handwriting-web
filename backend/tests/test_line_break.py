import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops, ImageFont
import handright._core as handright_core
from handright import Template

from app import apply_word_wrap, handwrite_with_page_breaks
from linebreak import CLOSING_PUNCTUATION, break_lines


FONT_PATH = Path(__file__).resolve().parents[1] / "font_assets" / "青叶手写体.ttf"

PAGE_WIDTH = 600
PAGE_HEIGHT = 400
FONT_SIZE = 40
MARGIN = 20


def fixed_advance(char):
    return 10


def latin_template():
    return Template(
        background=Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white"),
        font=ImageFont.truetype(str(FONT_PATH), size=FONT_SIZE),
        line_spacing=60,
        left_margin=MARGIN,
        top_margin=MARGIN,
        right_margin=MARGIN,
        bottom_margin=MARGIN,
        word_spacing=0,
        line_spacing_sigma=0,
        font_size_sigma=0,
        word_spacing_sigma=0,
        perturb_x_sigma=0,
        perturb_y_sigma=0,
        perturb_theta_sigma=0,
        ink_depth_sigma=0,
    )


def font_advance(template):
    font = template.get_font()

    def advance(char):
        left, _, right, _ = font.getbbox(char)
        return (right - left) + template.get_word_spacing()

    return advance


def rendered_lines(text, template):
    """Line contents as handright lays them out, without rendering pixels."""
    positioned = []

    def record_flow_layout(draw, x, y, char, tpl, rand):
        positioned.append((round(y), char))
        left, _, right, _ = tpl.get_font().getbbox(char)
        return x + (right - left) + tpl.get_word_spacing()

    with patch.object(handright_core, "_flow_layout", record_flow_layout):
        list(handright_core._draft(text, (template,), seed=1))

    chars_by_line = defaultdict(list)
    for y, char in positioned:
        chars_by_line[y].append(char)
    return ["".join(chars_by_line[y]) for y in sorted(chars_by_line)]


def words_of(lines):
    return [word for line in lines for word in line.split()]


class WordBreakTest(unittest.TestCase):
    def test_english_words_are_not_split(self):
        text = "The quick brown fox jumps over the lazy dog"

        lines = break_lines(text, fixed_advance, 100).split("\n")

        self.assertGreater(len(lines), 1)
        self.assertEqual(words_of(lines), text.split())

    def test_closing_punctuation_never_starts_a_line(self):
        text = (
            "Hello, world. This is a test of the emergency broadcast system; "
            "it should wrap nicely! Also (this) part [works] fine, right?"
        )

        lines = break_lines(text, fixed_advance, 100).split("\n")

        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertNotIn(line[:1], CLOSING_PUNCTUATION)

    def test_punctuation_separated_by_a_space_stays_on_the_previous_line(self):
        text = "aaaaaaaaa , c"

        lines = break_lines(text, fixed_advance, 100).split("\n")

        self.assertEqual(lines[0], "aaaaaaaaa ,")
        for line in lines:
            self.assertFalse(line.startswith(","))

    def test_overlong_word_is_still_broken(self):
        text = "start " + "z" * 30 + " end"

        lines = break_lines(text, fixed_advance, 100).split("\n")

        self.assertEqual(
            lines,
            ["start", "z" * 11, "z" * 11, "z" * 8, "end"],
        )

    def test_cjk_punctuation_hangs_instead_of_starting_a_line(self):
        text = "中" * 10 + "，" + " tail"

        lines = break_lines(text, fixed_advance, 100).split("\n")

        self.assertEqual(lines, ["中" * 10 + "，", "tail"])

    def test_cjk_only_text_is_left_untouched(self):
        text = "这是一段用来测试换行的中文文字，标点符号不应该出现在行首，比如逗号。"

        self.assertEqual(break_lines(text, fixed_advance, 100), text)

    def test_existing_newlines_and_blank_lines_are_preserved(self):
        text = "hello world\n\nsecond paragraph here"

        lines = break_lines(text, fixed_advance, 100).split("\n")

        self.assertEqual(lines[0], "hello")
        self.assertEqual(lines[1], "world")
        self.assertEqual(lines[2], "")
        self.assertEqual(lines[3], "second")
        self.assertEqual(words_of(lines), text.split())

    def test_breaks_do_not_leave_leading_or_trailing_spaces(self):
        text = "aaaa bbbb cccc dddd eeee ffff"

        lines = break_lines(text, fixed_advance, 100).split("\n")

        for line in lines:
            self.assertEqual(line, line.strip())

    def test_leading_indentation_is_kept(self):
        text = "    中文 内容"

        self.assertEqual(break_lines(text, fixed_advance, 100), text)


class HandrightAgreementTest(unittest.TestCase):
    def test_cjk_breaks_inside_a_mixed_paragraph_match_handright(self):
        template = latin_template()
        text = (
            "这是一段用来测试换行的中文文字， "
            "The quick brown fox jumps over the lazy dog."
        )

        old_lines = rendered_lines(text, template)
        new_lines = break_lines(
            text,
            font_advance(template),
            PAGE_WIDTH - 2 * MARGIN - FONT_SIZE,
        ).split("\n")

        def cjk_only(lines):
            return [line for line in lines if not any(ord(c) < 128 for c in line)]

        self.assertEqual(cjk_only(new_lines), ["这是一段用来测试换行的中文文字，"])
        self.assertEqual(cjk_only(new_lines), cjk_only(old_lines))
        self.assertEqual(
            words_of(new_lines[1:]), "The quick brown fox jumps over the lazy dog.".split()
        )

    def test_rendered_lines_are_the_computed_lines(self):
        template = latin_template()
        text = (
            "The quick brown fox jumps over the lazy dog and keeps running "
            "through the field."
        )
        wrapped = apply_word_wrap(text, template)

        self.assertEqual(rendered_lines(wrapped, template), wrapped.split("\n"))
        for line in wrapped.split("\n"):
            self.assertNotIn(line[:1], CLOSING_PUNCTUATION)


class ApplyWordWrapTest(unittest.TestCase):
    def test_cjk_text_is_left_untouched(self):
        template = latin_template()
        text = "这是一段用来测试换行的中文文字，标点符号不应该出现在行首，比如逗号。"

        self.assertEqual(apply_word_wrap(text, template), text)

    @patch("app.handwrite")
    def test_page_breaks_are_applied_after_wrapping(self, handwrite_mock):
        handwrite_mock.side_effect = lambda text, _: [text]
        template = latin_template()
        text = "The quick brown fox jumps over the lazy dog\n---\nsecond page"

        list(handwrite_with_page_breaks(text, template))

        first_chunk = handwrite_mock.call_args_list[0].args[0]
        self.assertIn("\n", first_chunk)
        self.assertEqual(
            words_of(first_chunk.split("\n")),
            "The quick brown fox jumps over the lazy dog".split(),
        )
        self.assertEqual(handwrite_mock.call_args_list[1].args[0], "second page")


class RenderTest(unittest.TestCase):
    def test_wrapped_latin_text_renders_inside_the_canvas(self):
        template = latin_template()
        text = (
            "The quick brown fox jumps over the lazy dog and keeps running "
            "through the field."
        )

        images = list(handwrite_with_page_breaks(text, template))

        self.assertEqual(len(images), 1)
        image = images[0]
        self.assertEqual(image.size, (PAGE_WIDTH, PAGE_HEIGHT))
        ink = ImageChops.difference(image, Image.new("RGB", image.size, "white"))
        bbox = ink.getbbox()
        self.assertIsNotNone(bbox)
        left, top, right, bottom = bbox
        self.assertGreaterEqual(left, MARGIN - 2)
        self.assertGreaterEqual(top, MARGIN - 2)
        self.assertLessEqual(right, PAGE_WIDTH - MARGIN)
        self.assertLessEqual(bottom, PAGE_HEIGHT - MARGIN)


if __name__ == "__main__":
    unittest.main()
