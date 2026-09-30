import pytest

from evalkit.templating import TemplateError, has_placeholders, render, render_value


def test_render_replaces_variables_and_dotted_paths():
    ctx = {"name": "Ada", "vars": {"city": "London"}, "items": ["a", "b"]}
    assert render("Hi {{ name }} from {{vars.city}}, {{items.1}}", ctx) == "Hi Ada from London, b"


def test_render_serializes_structures_as_json():
    assert render("{{ data }}", {"data": {"a": 1}}) == '{"a": 1}'
    assert render("[{{ none }}]", {"none": None}) == "[]"


def test_render_unknown_variable_raises():
    with pytest.raises(TemplateError, match="missing"):
        render("{{ missing }}", {})


def test_render_value_keeps_type_for_single_placeholder():
    ctx = {"n": 3, "prompt": "hello"}
    assert render_value("{{n}}", ctx) == 3
    assert render_value({"q": "{{prompt}}", "k": ["x {{n}}"], "z": 1}, ctx) == {
        "q": "hello",
        "k": ["x 3"],
        "z": 1,
    }


def test_has_placeholders():
    assert has_placeholders("a {{b}}")
    assert not has_placeholders("a {b}")
