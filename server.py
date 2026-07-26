"""soundboard: proof-of-concept server for SEP-0000 (displayTemplate / displayText).

A toy game-audio middleware server. Deliberately minimal: its only job is to
exercise the three rendering cases the SEP must handle.

  1. mix_set   — flat schema, scalar args       -> tool-level displayTemplate
  2. cue_ctl   — oneOf-branched schema          -> branch-scoped displayTemplate
  3. sfx_play  — dense packed patch string      -> call-side raw fallback,
                 (in the spirit of the sfxr        result-side displayText
                  base58 share codes)

Run:  python render_client.py   (spawns this server over stdio)
"""

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

import patchcodec

server = Server("soundboard")

# ---------------------------------------------------------------------------
# Tool declarations, exactly as they'd appear on the wire.
# ---------------------------------------------------------------------------

TOOLS = [
    types.Tool(
        name="mix_set",
        description="Set the gain of a mixer bus.",
        inputSchema={
            "type": "object",
            "properties": {
                "bus": {"type": "string"},
                "gain_db": {"type": "number"},
                "ramp_ms": {"type": "integer"},
            },
            "required": ["bus", "gain_db"],
        },
        annotations=types.ToolAnnotations(
            title="Set bus gain",
            readOnlyHint=False,
            # SEP §1: flat template, tool-level.
            displayTemplate="set {bus} bus to {gain_db} dB over {ramp_ms} ms",
        ),
    ),
    types.Tool(
        name="cue_ctl",
        description="Cue transport: play, stop, or duck a bus under dialogue.",
        inputSchema={
            "oneOf": [
                {
                    "title": "play",
                    # SEP §1: branch-scoped template.
                    "displayTemplate": "play cue {cue}",
                    "type": "object",
                    "properties": {
                        "cue": {"type": "string"},
                        "fade_ms": {"type": "integer"},
                    },
                    "required": ["cue"],
                    "additionalProperties": False,
                },
                {
                    "title": "stop",
                    "displayTemplate": "stop cue {cue}",
                    "type": "object",
                    "properties": {"cue": {"type": "string"}, "stop": {"const": True}},
                    "required": ["cue", "stop"],
                    "additionalProperties": False,
                },
                {
                    "title": "duck",
                    "displayTemplate": "duck {bus} by {amount_db} dB",
                    "type": "object",
                    "properties": {
                        "bus": {"type": "string"},
                        "amount_db": {"type": "number"},
                    },
                    "required": ["bus", "amount_db"],
                    "additionalProperties": False,
                },
            ]
        },
        annotations=types.ToolAnnotations(title="Cue control"),
    ),
    types.Tool(
        name="sfx_play",
        description=(
            "Synthesize and play a sound effect from a packed patch string "
            "(fixed-width base36 fields; see patchcodec.py)."
        ),
        inputSchema={
            "type": "object",
            "properties": {"patch": {"type": "string"}},
            "required": ["patch"],
        },
        annotations=types.ToolAnnotations(
            title="Play SFX patch",
            # Best a static template can do for an encoded argument: exhibit
            # it verbatim in a labeled frame. The SEP's Limitations section
            # is honest about this; the result side is where the server,
            # the only party that understands its own encoding, closes the
            # gap via displayText.
            displayTemplate="play patch {patch}",
        ),
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "mix_set":
        state = {"bus": arguments["bus"], "gain_db": arguments["gain_db"], "ok": True}
        display = f"{arguments['bus']} bus set to {arguments['gain_db']} dB"
    elif name == "cue_ctl":
        state = {"ack": True, **arguments}
        display = "cue command acknowledged"
    elif name == "sfx_play":
        p = patchcodec.decode(arguments["patch"])
        length_ms = p["attack_ms"] + p["sustain_ms"] + p["decay_ms"]
        state = {**p, "rendered_ms": length_ms}
        display = (
            f"{p['wave']} wave @ {p['freq_hz']} Hz, {length_ms / 1000:.2f} s "
            f"envelope — {patchcodec.characterize(p)}"
        )
    else:
        raise ValueError(f"unknown tool {name}")

    return [
        types.TextContent(
            type="text",
            text=str(state),  # model-facing payload, compact
            # SEP §2: already-rendered, per-response human summary.
            annotations=types.Annotations(displayText=display),
        )
    ]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
