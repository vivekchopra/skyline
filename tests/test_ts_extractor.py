import shutil

import pytest

from skyline.ts_client import extract_modules

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npm") is None,
    reason="TypeScript tests need Node.js + npm on PATH",
)


def test_extract_class_and_interface():
    src = """
interface Gateway {
  send(amount: number): Promise<boolean>;
}

class PaymentProcessor implements Gateway {
  async send(amount: number): Promise<boolean> {
    return true;
  }
}
"""
    modules = extract_modules({"pay.ts": src})
    mod = modules["pay.ts"]
    assert mod.language == "typescript"
    assert "Gateway" in mod.types
    assert mod.types["Gateway"].kind == "interface"
    assert "PaymentProcessor" in mod.types
    cls = mod.types["PaymentProcessor"]
    assert cls.kind == "class"
    assert ("Gateway", "implements") in cls.relations
    assert "async" in cls.members["send"].modifiers
    assert cls.members["send"].return_type == "Promise<boolean>"


def test_extends_and_decorators():
    src = """
class Base {}

@Injectable()
class Derived extends Base {
  private x: number = 1;
}
"""
    modules = extract_modules({"a.ts": src})
    derived = modules["a.ts"].types["Derived"]
    assert ("Base", "extends") in derived.relations
    assert derived.decorators == ["Injectable()"]
    assert derived.members["x"].kind == "property"
    assert "private" in derived.members["x"].modifiers


def test_top_level_function_and_arrow_export():
    src = """
export function add(a: number, b: number): number {
  return a + b;
}

export const mul = (a: number, b: number): number => a * b;
"""
    modules = extract_modules({"m.ts": src})
    fns = modules["m.ts"].functions
    assert fns["add"].params == ["a: number", "b: number"]
    assert fns["add"].return_type == "number"
    assert fns["mul"].exported is True
    assert fns["mul"].params == ["a: number", "b: number"]


def test_complexity_and_interface_methods_have_none():
    src = """
interface Gateway {
  send(amount: number): Promise<boolean>;
}

class Foo {
  branchy(x: number, y: number): number {
    if (x && y) {
      for (let i = 0; i < x; i++) {
        if (i > 0) return i;
      }
    }
    return 0;
  }
}
"""
    modules = extract_modules({"m.ts": src})
    # interface methods have no body -> complexity is None
    assert modules["m.ts"].types["Gateway"].members["send"].complexity is None
    # base(1) + if(1) + &&(1) + for(1) + if(1) = 5
    assert modules["m.ts"].types["Foo"].members["branchy"].complexity == 5
