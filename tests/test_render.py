from skyline.diff import diff_models
from skyline.python_extractor import extract_module as py_extract
from skyline.render_svg import build_diagram_svg


def test_same_short_name_classes_both_appear():
    base = {
        "billing/client.py": py_extract("billing/client.py", "class Client:\n    pass\n"),
        "shipping/client.py": py_extract("shipping/client.py", "class Client:\n    pass\n"),
    }
    head = {
        "billing/client.py": py_extract("billing/client.py", "class Client:\n    def go(self):\n        return 1\n"),
        "shipping/client.py": py_extract("shipping/client.py", "class Client:\n    def go(self):\n        return 2\n"),
    }
    svg = build_diagram_svg(diff_models(base, head))
    assert "billing/client.py" in svg
    assert "shipping/client.py" in svg
    assert svg.count(">Client<") >= 2


def test_changed_free_function_appears():
    base = {"m.py": py_extract("m.py", "def helper():\n    return 1\n")}
    head = {"m.py": py_extract("m.py", "def helper():\n    return 2\n")}
    svg = build_diagram_svg(diff_models(base, head))
    assert "\u00abfunction\u00bb" in svg
    assert "helper" in svg
