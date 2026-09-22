// Structural extractor for TypeScript/TSX, using the TypeScript compiler
// API to parse source text (no type-checking, no tsconfig needed — this
// only needs syntax, not resolved types, so it works on individual changed
// files in isolation).
//
// Protocol: reads a JSON array of {path, source} objects from stdin,
// writes a JSON array of module models (see skyline/model.py for the
// shape each object mirrors) to stdout.
'use strict';

const ts = require('typescript');

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

function hasModifier(node, kind) {
  const mods = ts.canHaveModifiers(node) ? ts.getModifiers(node) : undefined;
  return !!(mods && mods.some((m) => m.kind === kind));
}

function modifierList(node) {
  const out = [];
  if (hasModifier(node, ts.SyntaxKind.PublicKeyword)) out.push('public');
  if (hasModifier(node, ts.SyntaxKind.PrivateKeyword)) out.push('private');
  if (hasModifier(node, ts.SyntaxKind.ProtectedKeyword)) out.push('protected');
  if (hasModifier(node, ts.SyntaxKind.StaticKeyword)) out.push('static');
  if (hasModifier(node, ts.SyntaxKind.ReadonlyKeyword)) out.push('readonly');
  if (hasModifier(node, ts.SyntaxKind.AbstractKeyword)) out.push('abstract');
  if (hasModifier(node, ts.SyntaxKind.AsyncKeyword)) out.push('async');
  return out;
}

function decoratorList(node) {
  const decos = ts.canHaveDecorators(node) ? ts.getDecorators(node) : undefined;
  if (!decos) return [];
  return decos.map((d) => d.expression.getText().trim());
}

function isExported(node) {
  return hasModifier(node, ts.SyntaxKind.ExportKeyword) ||
    hasModifier(node, ts.SyntaxKind.DefaultKeyword);
}

function paramList(params) {
  return params.map((p) => {
    const name = p.name.getText();
    const opt = p.questionToken ? '?' : '';
    const type = p.type ? `: ${p.type.getText()}` : '';
    return `${name}${opt}${type}`;
  });
}

function isFunctionLike(n) {
  return ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n) ||
    ts.isMethodDeclaration(n) || ts.isGetAccessor(n) || ts.isSetAccessor(n) || ts.isConstructorDeclaration(n);
}

// Cyclomatic complexity: 1 + one per decision point. Does not descend into
// nested function-like nodes -- each unit's complexity stays scoped to
// itself (mirrors python_extractor.py's approach, for the same reason: a
// nested arrow function inside a method isn't extracted as its own
// member, so folding its branches into the parent would be confusing, not
// more accurate).
function computeComplexity(root) {
  let complexity = 1;
  const branchKinds = new Set([
    ts.SyntaxKind.IfStatement,
    ts.SyntaxKind.ForStatement,
    ts.SyntaxKind.ForInStatement,
    ts.SyntaxKind.ForOfStatement,
    ts.SyntaxKind.WhileStatement,
    ts.SyntaxKind.DoStatement,
    ts.SyntaxKind.CatchClause,
    ts.SyntaxKind.ConditionalExpression,
    ts.SyntaxKind.CaseClause,
  ]);
  const logicalOps = new Set([
    ts.SyntaxKind.AmpersandAmpersandToken,
    ts.SyntaxKind.BarBarToken,
    ts.SyntaxKind.QuestionQuestionToken,
  ]);

  function visit(node, isRoot) {
    if (!isRoot && isFunctionLike(node)) return;
    if (branchKinds.has(node.kind)) {
      complexity += 1;
    } else if (ts.isBinaryExpression(node) && node.operatorToken && logicalOps.has(node.operatorToken.kind)) {
      complexity += 1;
    }
    ts.forEachChild(node, (child) => visit(child, false));
  }

  visit(root, true);
  return complexity;
}

function bodyComplexity(node) {
  // Signature-only members (interface methods, abstract methods without a
  // body) have no complexity to measure.
  if (!node.body) return null;
  return computeComplexity(node);
}

function extractMembers(members) {
  const out = {};
  for (const m of members) {
    let kind = null;
    let params = [];
    let returnType = null;
    let name = null;
    let complexity = null;
    const optional = !!m.questionToken;

    if (ts.isMethodDeclaration(m) || ts.isMethodSignature(m)) {
      kind = 'method';
      name = m.name ? m.name.getText() : '(anonymous)';
      params = paramList(m.parameters);
      returnType = m.type ? m.type.getText() : null;
      complexity = bodyComplexity(m);
    } else if (ts.isConstructorDeclaration(m)) {
      kind = 'method';
      name = 'constructor';
      params = paramList(m.parameters);
      complexity = bodyComplexity(m);
    } else if (ts.isPropertyDeclaration(m) || ts.isPropertySignature(m)) {
      kind = 'property';
      name = m.name ? m.name.getText() : '(anonymous)';
      returnType = m.type ? m.type.getText() : null;
    } else if (ts.isGetAccessor(m)) {
      kind = 'property';
      name = m.name.getText();
      returnType = m.type ? m.type.getText() : null;
      complexity = bodyComplexity(m);
    } else if (ts.isSetAccessor(m)) {
      kind = 'method';
      name = m.name.getText();
      params = paramList(m.parameters);
      complexity = bodyComplexity(m);
    } else {
      continue;
    }

    out[name] = {
      name,
      kind,
      params,
      modifiers: modifierList(m),
      return_type: returnType,
      optional,
      complexity,
    };
  }
  return out;
}

function extractHeritage(node) {
  const relations = [];
  const clauses = node.heritageClauses || [];
  for (const clause of clauses) {
    const kind = clause.token === ts.SyntaxKind.ExtendsKeyword ? 'extends' : 'implements';
    for (const t of clause.types) {
      relations.push([t.expression.getText(), kind]);
    }
  }
  return relations;
}

function extractFile(path, source) {
  const scriptKind = path.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, scriptKind);

  const types = {};
  const functions = {};

  function addFunction(node, name) {
    functions[name] = {
      name,
      params: paramList(node.parameters),
      modifiers: modifierList(node),
      return_type: node.type ? node.type.getText() : null,
      exported: isExported(node),
      complexity: bodyComplexity(node),
    };
  }

  for (const node of sf.statements) {
    if (ts.isClassDeclaration(node) && node.name) {
      types[node.name.text] = {
        name: node.name.text,
        kind: 'class',
        decorators: decoratorList(node),
        relations: extractHeritage(node),
        members: extractMembers(node.members),
        exported: isExported(node),
      };
    } else if (ts.isInterfaceDeclaration(node)) {
      types[node.name.text] = {
        name: node.name.text,
        kind: 'interface',
        decorators: [],
        relations: extractHeritage(node),
        members: extractMembers(node.members),
        exported: isExported(node),
      };
    } else if (ts.isFunctionDeclaration(node) && node.name) {
      addFunction(node, node.name.text);
    } else if (ts.isVariableStatement(node)) {
      const exported = isExported(node);
      for (const decl of node.declarationList.declarations) {
        const init = decl.initializer;
        const isFnLike = init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init));
        if (isFnLike && ts.isIdentifier(decl.name)) {
          functions[decl.name.text] = {
            name: decl.name.text,
            params: paramList(init.parameters),
            modifiers: modifierList(init),
            return_type: init.type ? init.type.getText() : null,
            exported,
            complexity: bodyComplexity(init),
          };
        }
      }
    }
  }

  return { path, language: 'typescript', types, functions, imports: [] };
}

async function main() {
  const raw = await readStdin();
  const files = JSON.parse(raw || '[]');
  const out = files.map((f) => {
    try {
      return extractFile(f.path, f.source);
    } catch (err) {
      // A single malformed file shouldn't kill the whole batch.
      return { path: f.path, language: 'typescript', types: {}, functions: {}, imports: [], error: String(err) };
    }
  });
  process.stdout.write(JSON.stringify(out));
}

main().catch((err) => {
  process.stderr.write(String((err && err.stack) || err));
  process.exit(1);
});
