# AHA! "host" is in _HOP_BY_HOP!
# So `kl in _HOP_BY_HOP` is True, so it does `continue`.
# It NEVER reaches `if kl == "host": headers[key] = f"localhost:{port}"`!
# This means line 189 is DEAD CODE.
# Let's fix `wp_proxy.py` to either remove "host" from _HOP_BY_HOP or remove the dead code.
# The comment says:
# ```
#         if kl in _HOP_BY_HOP:
#             continue
#         if kl == "host":
#             headers[key] = f"localhost:{port}"
# ```
# If `host` is in `_HOP_BY_HOP`, it's dropped, so httpx will automatically inject the `host` based on the target URL (which is localhost).
# Actually, httpx calculates the `Host` header based on the URL anyway, unless you explicitly set it.
# So dropping `host` is totally fine, and the subsequent `if kl == "host":` check is unreachable.
# I will just remove `host` from `_HOP_BY_HOP` if they wanted to explicitly set it to `localhost:{port}`, or I will remove the dead code block.
# Actually, the logic *wants* to overwrite the host header!
# If it's dropped in `_HOP_BY_HOP`, `httpx` will use `localhost:8081` anyway because the target URL is `http://localhost:{port}/...`.
# It's better to just remove `"host"` from `_HOP_BY_HOP` so the explicit logic runs. Or remove the explicit logic.
# Wait, let's remove `"host"` from `_HOP_BY_HOP`.
