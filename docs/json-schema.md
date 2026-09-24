# JSON report

`skyline diff --format json` writes this object. It is the HTML report's sections as data. The `risk` array is every scored unit, highest CRAP first. The HTML page still shows a short summary of that list.

```json
{
  "base": "main",
  "head": "feature",
  "stats": {"types_added": 0, "types_removed": 0, "types_modified": 0, "functions_added": 0, "functions_removed": 0, "functions_modified": 0, "members_added": 0, "members_removed": 0, "members_modified": 0},
  "violations": [{"kind": "illegal_edge", "message": "", "is_new": true}],
  "types": [{"name": "", "qualname": "", "path": "", "kind": "class", "status": "modified", "reason": "", "line": 1, "end_line": 4, "added_relations": [], "removed_relations": [], "members": [{"name": "", "status": "modified", "reason": "", "line": 2, "end_line": 3, "crap": {"value": 2, "band": "low", "complexity": 1, "coverage": 0, "coverage_supplied": false, "label": "CRAP 2"}}]}],
  "functions": [{"name": "", "qualname": "", "path": "", "status": "modified", "reason": "", "line": 1, "end_line": 2, "crap": null}],
  "breaking": [{"text": "", "path": "", "line": 1, "end_line": 2, "side": "head"}],
  "risk": [{"name": "", "path": "", "line": 1, "end_line": 2, "crap": {"value": 2, "band": "low", "complexity": 1, "coverage": 0, "coverage_supplied": false, "label": "CRAP 2"}}],
  "coupling": ["a.py → b.py"],
  "untested": ["a.py::NewType"],
  "data_model": [{"name": "", "qualname": "", "path": "", "status": "added", "relations": [], "columns": [{"name": "", "status": "added", "before": null, "after": "int"}]}]
}
```

`side` is `head` for the commit under review and `base` for a removal. `crap` is null when the unit has no body to score. Unchanged types, functions, imports, and columns are omitted.
