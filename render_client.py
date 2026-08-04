"""Reference client-side renderer for SEP-0000.

Connects to server.py over stdio, then for a set of example calls prints
what a client shows TODAY (raw JSON) next to what it shows WITH the SEP.

Implements the SEP's normative rules:
  * {name} placeholders reference top-level scalar args only
  * missing / non-scalar values render as "..."
  * "{{" and "}}" are literal braces
  * oneOf/anyOf: first branch (document order) the args validate against wins
  * args supplied but unreferenced by the matched template -> trailing
    "[+N more args]" marker (omission mitigation, SEP Security Implications)
  * unmatched branch or no template -> fall back to raw argument display
  * substituted values are untrusted text (here: terminal, printed literally)
"""

import asyncio
import json
import re
import sys

import jsonschema

NS = "io.modelcontextprotocol/display-templates"
NS_BRANCH = "io.modelcontextprotocol/display-template"
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import patchcodec

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def substitute(template: str, args: dict) -> str:
    """SEP §1 substitution: literal, no expressions, no failures."""
    tmp = template.replace("{{", "\x00").replace("}}", "\x01")

    def repl(m):
        v = args.get(m.group(1))
        return str(v) if isinstance(v, (str, int, float, bool)) else "..."

    out = PLACEHOLDER.sub(repl, tmp)
    return re.sub(r"\s+", " ", out.replace("\x00", "{").replace("\x01", "}")).strip()


def referenced(template: str) -> set[str]:
    """Placeholder names a template actually renders ({{ }} escapes excluded)."""
    return set(PLACEHOLDER.findall(template.replace("{{", "\x00").replace("}}", "\x01")))


def preview(template: str, args: dict, branch: dict | None = None) -> str:
    """Substitute, then flag supplied args the template does not reference.

    SEP Security Implications: a template that renders only a subset of the
    supplied arguments could show an innocuous line while concealing the
    argument that matters, so the client visibly counts what it isn't showing.
    Discriminator carve-out: an argument whose value is pinned by the matched
    branch's schema (a `const`) is communicated by the template's selection
    itself, so it does not count as concealed.
    """
    text = substitute(template, args)
    shown = referenced(template)
    if branch:
        for name, prop in branch.get("properties", {}).items():
            if isinstance(prop, dict) and "const" in prop:
                shown.add(name)
    hidden = len(set(args) - shown)
    if hidden:
        text += f" [+{hidden} more arg{'s' if hidden != 1 else ''}]"
    return text


def render_call(tool, args: dict) -> str | None:
    """Return the human preview for a call, or None (client falls back to raw)."""
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
    branches = schema.get("oneOf") or schema.get("anyOf")
    if branches:
        for branch in branches:  # document order = tie-break
            try:
                jsonschema.validate(args, branch)
            except jsonschema.ValidationError:
                continue
            btmpl = branch.get(NS_BRANCH) or branch.get("displayTemplate")
            if btmpl:
                return preview(btmpl, args, branch)
            break  # matched a branch with no template -> tool-level fallback
    ann = tool.annotations
    # `_meta` first (the carrier that survives SDK 2.x strict models),
    # annotations second (1.x-era servers whose models kept extra keys).
    meta = getattr(tool, "meta", None) or {}
    tmpl = (meta.get(NS) or {}).get("template") or meta.get("displayTemplate") or (
        getattr(ann, "displayTemplate", None) if ann else None
    )
    return preview(tmpl, args) if tmpl else None


def render_result(result) -> str | None:
    """SEP §2: use the block's displayText if present."""
    for block in result.content:
        ann = getattr(block, "annotations", None)
        bmeta = getattr(block, "meta", None) or {}
        text = (bmeta.get(NS) or {}).get("text") or bmeta.get("displayText") or (
            getattr(ann, "displayText", None) if ann else None
        )
        if text:
            return text
    return None


# Dense patch blobs, built the way a model would supply them: pre-encoded.
COIN = patchcodec.encode("square", 988, 5, 60, 220, 55, 25)
BOOM = patchcodec.encode("noise", 110, 0, 90, 640, 20, 30)

EXAMPLE_CALLS = [
    ("mix_set", {"bus": "music", "gain_db": -6.0, "ramp_ms": 250}),
    ("mix_set", {"bus": "sfx", "gain_db": 0.0}),            # optional arg missing
    ("mix_set", {"bus": "voice", "gain_db": -60.0,
                 "duck_others": True}),                     # arg the template
                                                            # doesn't reference
                                                            # -> [+1 more arg]
    ("cue_ctl", {"cue": "boss_theme", "fade_ms": 1200}),    # branch: play
    ("cue_ctl", {"cue": "boss_theme", "stop": True}),       # branch: stop
    ("cue_ctl", {"bus": "music", "amount_db": -12}),        # branch: duck
    ("sfx_play", {"patch": COIN}),                          # dense encoded string
    ("sfx_play", {"patch": BOOM}),
]


async def main():
    params = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}

            w = 56
            print(f"{'WITHOUT SEP (what clients show today)':<{w}}| WITH SEP")
            print("-" * w + "+" + "-" * 44)
            for name, args in EXAMPLE_CALLS:
                raw = f"{name} {json.dumps(args)}"
                preview = render_call(tools[name], args) or "(raw fallback)"
                print(f"{raw:<{w}}| {preview}")

                result = await session.call_tool(name, args)
                raw_r = f"  -> {result.content[0].text}"
                nice = render_result(result)
                print(f"{raw_r:<{w}}| {'  -> ' + nice if nice else '  (raw)'}")
            print()
            print("Note mix_set #3: 'duck_others' is supplied but the template")
            print("doesn't reference it, so the renderer appends [+1 more arg]")
            print("rather than let a partial template conceal an argument")
            print("(SEP Security Implications, call-side omission).")
            print()
            print("Note sfx_play: the call-side template can only exhibit the")
            print("packed patch verbatim (SEP Limitations §4), the same problem")
            print("as an sfxr/jsfxr base58 share code. The result-side")
            print("displayText, rendered by the server that alone understands")
            print("its encoding, is fully legible. Pre-execution legibility for")
            print("encoded calls is deferred to SEP-1862-style resolution.")


if __name__ == "__main__":
    asyncio.run(main())
