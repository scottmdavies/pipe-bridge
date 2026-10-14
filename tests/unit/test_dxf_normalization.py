from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import ezdxf

from digital_workshop.services.dxf_normalization import DxfNormalizer


def _make_dxf(text: str) -> bytes:
    document = ezdxf.new("R2018")
    document.modelspace().add_mtext(text)
    output = StringIO()
    document.write(output)
    return output.getvalue().encode("utf-8")


def _libredwg_wrap(text: str) -> bytes:
    lines = _make_dxf(text).decode("utf-8").splitlines()
    mtext_start = next(
        index
        for index in range(len(lines) - 1)
        if lines[index].strip() == "0" and lines[index + 1] == "MTEXT"
    )
    mtext_end = next(
        index for index in range(mtext_start + 2, len(lines) - 1, 2) if lines[index].strip() == "0"
    )
    text_start = next(
        index
        for index in range(mtext_start + 2, mtext_end, 2)
        if lines[index].strip() in {"1", "3"}
    )
    text_end = text_start
    while text_end < mtext_end and lines[text_end].strip() in {"1", "3"}:
        text_end += 2

    malformed_tags = ["  1", text[:255], "  3", text[255:510], text[510:]]
    return "\r\n".join(lines[:text_start] + malformed_tags + lines[text_end:]).encode("utf-8")


def test_repairs_wrapped_mtext_and_preserves_text(tmp_path: Path) -> None:
    text = "A" * 255 + "B" * 462
    result = DxfNormalizer().normalize(_libredwg_wrap(text))

    assert result.applied_rules == ("mtext_fixed_width_wrap",)
    path = tmp_path / "normalized.dxf"
    path.write_bytes(result.content)
    document = ezdxf.readfile(path)
    mtext = next(entity for entity in document.modelspace() if entity.dxftype() == "MTEXT")
    assert mtext.text == text

    lines = result.content.decode("utf-8").splitlines()
    mtext_start = next(
        index
        for index in range(len(lines) - 1)
        if lines[index].strip() == "0" and lines[index + 1] == "MTEXT"
    )
    group_codes: list[int] = []
    for index in range(mtext_start + 2, len(lines) - 1, 2):
        code = int(lines[index].strip())
        if code == 0:
            break
        if code in (1, 3):
            group_codes.append(code)
    assert group_codes[-1] == 1
    assert set(group_codes[:-1]) <= {3}


def test_valid_dxf_is_unchanged() -> None:
    content = _make_dxf("ordinary MTEXT")

    result = DxfNormalizer().normalize(content)

    assert result.content == content
    assert result.applied_rules == ()


def test_unrecognized_broken_pair_is_left_for_parser() -> None:
    content = b"  0\nSECTION\n  1\nHEADER\nnot a group code\n"

    result = DxfNormalizer().normalize(content)

    assert result.content == content
    assert result.applied_rules == ()


def test_dwg_import_normalizes_converter_output(workshop) -> None:
    text = "A" * 255 + "B" * 462
    malformed_dxf = _libredwg_wrap(text)
    workshop._dwg_converter = SimpleNamespace(convert=lambda _: malformed_dxf)

    drawing = workshop.import_drawing("notes.dwg", b"AC1032")

    assert drawing.filename == "notes.dwg"
