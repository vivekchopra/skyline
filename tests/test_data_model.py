from skyline.diff import diff_models
from skyline.prisma_extractor import extract_prisma
from skyline.python_extractor import extract_module as py_extract
from skyline.render_html import build_html_report
from skyline.render_svg import build_data_svg, build_diagram_svg


DJANGO_BEFORE = """
from django.db import models

class User(models.Model):
    name = models.CharField(max_length=10)
"""

DJANGO_AFTER = """
from django.db import models

class User(models.Model):
    name = models.CharField(max_length=10)
    email = models.EmailField()
"""


def test_django_added_column_is_a_modified_table_not_a_class_member():
    diff = diff_models(
        {"app/models.py": py_extract("app/models.py", DJANGO_BEFORE)},
        {"app/models.py": py_extract("app/models.py", DJANGO_AFTER)},
    )
    table = next(t for t in diff.tables if t.name == "User")
    assert table.status == "modified"
    assert any(c.name == "email" and c.status == "added" for c in table.columns)
    cls = next(t for t in diff.types if t.name == "User")
    assert all(m.name != "email" for m in cls.members)

    class_svg = build_diagram_svg(diff)
    data_svg = build_data_svg(diff)
    assert "email" not in class_svg
    assert "email" in data_svg
    html = build_html_report(diff, "base", "head")
    assert "Data model" in html
    assert html.index("Data model") > html.index("diagram")
    assert "email" in html


def test_sqlalchemy_column_and_prisma_model():
    before = py_extract("db.py", "from sqlalchemy import Column, Integer, String\nclass User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer)\n")
    after = py_extract("db.py", "from sqlalchemy import Column, Integer, String\nclass User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer)\n    name = Column(String)\n")
    diff = diff_models({"db.py": before}, {"db.py": after})
    table = next(t for t in diff.tables if t.name == "users")
    assert table.status == "modified"
    assert any(c.name == "name" and c.status == "added" for c in table.columns)

    base = extract_prisma("schema.prisma", "model User {\n  id Int @id\n  name String\n}\n")
    head = extract_prisma("schema.prisma", "model User {\n  id Int @id\n  name String\n  email String\n}\n")
    prisma_diff = diff_models({"schema.prisma": base}, {"schema.prisma": head})
    prisma_table = next(t for t in prisma_diff.tables if t.name == "User")
    assert any(c.name == "email" and c.status == "added" for c in prisma_table.columns)
    assert "email" in build_data_svg(prisma_diff)
