import ast
import os

routes_dir = 'src/pit_panel/web/routes/'
issues = []

for root, _, files in os.walk(routes_dir):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                try:
                    tree = ast.parse(content)
                except Exception as e:
                    print(f"Error parsing {path}: {e}")
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        is_route = False
                        route_method = None
                        route_url = None

                        for dec in node.decorator_list:
                            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                                if isinstance(dec.func.value, ast.Name) and dec.func.value.id in ('router', 'app'):
                                    is_route = True
                                    route_method = dec.func.attr.upper()
                                    if dec.args and isinstance(dec.args[0], ast.Constant):
                                        route_url = dec.args[0].value

                        if is_route:
                            # Let's check returns
                            for subnode in ast.walk(node):
                                if isinstance(subnode, ast.Return):
                                    if subnode.value is None:
                                        val = "None"
                                    elif isinstance(subnode.value, ast.Constant):
                                        val = str(subnode.value.value)
                                    elif isinstance(subnode.value, ast.Dict):
                                        val = "dict{...}"
                                    elif isinstance(subnode.value, ast.List):
                                        val = "list[...]"
                                    elif isinstance(subnode.value, ast.Tuple):
                                        val = "tuple(...)"
                                    else:
                                        try:
                                            import astunparse
                                            val = astunparse.unparse(subnode.value).strip()
                                        except ImportError:
                                            val = "complex_expr"

                                    if val.startswith("dict") or val.startswith("list") or val.startswith("tuple") or val in ("True", "False") or (isinstance(subnode.value, ast.Constant) and isinstance(subnode.value.value, str) and not subnode.value.value.startswith("<") and not subnode.value.value.startswith("\n<")):
                                        # But wait, what if it returns HTML directly as string?
                                        pass

                                    # print(f"{route_method} {route_url} ({f}): return {val}")
