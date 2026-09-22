import ast, hashlib

class _Alpha(ast.NodeTransformer):
    """Alpha-rename bound names to canonical v0,v1,... (first appearance);
    strip docstrings. Unbound names (builtins, prompt-level refs) stay."""
    def __init__(self):
        self.map = {}
    def _bind(self, name):
        if name not in self.map:
            self.map[name] = f'v{len(self.map)}'
        return self.map[name]
    def visit_FunctionDef(self, node):
        node.name = self._bind(node.name)
        for a in list(node.args.args) + list(node.args.posonlyargs) + list(node.args.kwonlyargs):
            a.arg = self._bind(a.arg)
            a.annotation = None
        if node.args.vararg: node.args.vararg.arg = self._bind(node.args.vararg.arg)
        if node.args.kwarg: node.args.kwarg.arg = self._bind(node.args.kwarg.arg)
        node.returns = None
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:] or [ast.Pass()]
        self.generic_visit(node)
        return node
    visit_AsyncFunctionDef = visit_FunctionDef
    def visit_ClassDef(self, node):
        node.name = self._bind(node.name)
        self.generic_visit(node)
        return node
    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            node.id = self._bind(node.id)
        elif node.id in self.map:
            node.id = self.map[node.id]
        return node
    def visit_alias(self, node):
        as_ = node.asname or node.name.split('.')[0]
        node.asname = self._bind(as_)
        return node
    def visit_ExceptHandler(self, node):
        if node.name: node.name = self._bind(node.name)
        self.generic_visit(node)
        return node

def shape_of(sol):
    if not sol:
        return 'EMPTY'
    try:
        tree = ast.parse(sol)
        # two passes: bind all definitions first (handles use-before-def of helpers)
        a = _Alpha()
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                a._bind(n.name)
        tree = a.visit(tree)
        if (isinstance(tree, ast.Module) and tree.body and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str)):
            tree.body = tree.body[1:]
        return 'S:' + hashlib.sha1(ast.unparse(tree).encode()).hexdigest()[:16]
    except Exception:
        return 'SYNTAX:' + hashlib.sha1(sol.encode()).hexdigest()[:16]
