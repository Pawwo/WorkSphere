from app.services.latex_utils import coerce_latex_text, escape_latex, normalize_tex_chars


def test_escape_latex_special_chars():
    assert r"\_" in escape_latex("foo_bar")
    assert r"\&" in escape_latex("A & B")


def test_normalize_tex_chars():
    assert "--" in normalize_tex_chars("a\u2013b")


def test_escape_latex_accepts_list_from_llm():
    assert "Hello world" in escape_latex(["Hello", "world"])
    assert coerce_latex_text(["A", "B"]) == "A B"
