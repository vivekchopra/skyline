from skyline.python_extractor import extract_module


def test_extract_class_and_methods():
    src = """
class Foo(Base):
    def bar(self, x):
        return x
"""
    mod = extract_module("foo.py", src)
    assert "Foo" in mod.types
    cls = mod.types["Foo"]
    assert cls.kind == "class"
    assert cls.relations == [("Base", "extends")]
    assert "bar" in cls.members
    assert cls.members["bar"].params == ["self", "x"]
    assert cls.members["bar"].kind == "method"


def test_extract_function():
    src = "def helper(a, b=1):\n    return a + b\n"
    mod = extract_module("m.py", src)
    assert "helper" in mod.functions
    assert mod.functions["helper"].params == ["a", "b"]


def test_private_and_decorated_methods():
    src = """
class Foo:
    @property
    def value(self):
        return self._v

    @staticmethod
    def make():
        return Foo()
"""
    mod = extract_module("foo.py", src)
    cls = mod.types["Foo"]
    assert cls.members["value"].modifiers == ["property"]
    assert cls.members["make"].modifiers == ["staticmethod"]


def test_async_method_modifier():
    src = "class Foo:\n    async def go(self):\n        pass\n"
    mod = extract_module("foo.py", src)
    assert "async" in mod.types["Foo"].members["go"].modifiers


def test_cyclomatic_complexity():
    src = """
class Foo:
    def simple(self):
        return 1

    def branchy(self, x, y):
        if x and y:
            for i in range(x):
                if i > 0:
                    return i
        return 0
"""
    mod = extract_module("foo.py", src)
    assert mod.types["Foo"].members["simple"].complexity == 1
    # base(1) + if(1) + boolop-and(1) + for(1) + if(1) = 5
    assert mod.types["Foo"].members["branchy"].complexity == 5


def test_syntax_error_is_tolerated():
    mod = extract_module("broken.py", "def f(:\n")
    assert mod.types == {}
    assert mod.functions == {}
