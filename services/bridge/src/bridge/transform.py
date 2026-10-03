"""AIMC 2.0 transformations: Lua code with an `aimc_main(sources)` entry point (Transformation Blob).

`sources` is a table {SourceId = value}; the return value is written to the sinks (nil = do not write). The
code comes from the AAS server, so it runs in a sandbox: only pure functions and the string/table/math
libraries are visible (no os, io, require, load or Python access)."""

from __future__ import annotations

from lupa import LuaError, LuaRuntime

SAFE_GLOBALS = ("string", "table", "math", "tostring", "tonumber", "type", "pairs", "ipairs", "next",
                "select", "pcall", "error", "assert")
_LUA = LuaRuntime(register_eval=False, register_builtins=False, unpack_returned_tuples=True)
_SANDBOX_LOADER = _LUA.eval("""
function(code, names)
  local env = {}
  for _, name in ipairs(names) do env[name] = _G[name] end
  local chunk, err = load(code, "=aimc", "t", env)
  if not chunk then error(err) end
  chunk()
  if type(env.aimc_main) ~= "function" then error("no aimc_main(sources) function") end
  return env.aimc_main
end""")


class TransformationError(ValueError):
    pass


class Transformation:
    def __init__(self, code: str):
        self.code = code
        try:
            self._main = _SANDBOX_LOADER(code, _LUA.table(*SAFE_GLOBALS))
        except LuaError as exc:
            raise TransformationError(str(exc)) from exc

    def __call__(self, sources: dict):
        try:
            result = self._main(_LUA.table_from(sources))
        except LuaError:
            return None
        return result
