# soundboard: SEP-0000 proof of concept

Minimal demonstration of `displayTemplate` (call-side) and `displayText`
(result-side) from SEP-0000, using the unmodified Python MCP SDK (2.x). The toy
domain is game-audio middleware: a mixer, a cue transport, and a retro SFX
synthesizer.

## Why game audio?

Dense, machine-optimized encodings that humans can't read at a glance have
been part of game audio tooling for decades. The canonical modern example is
the sfxr family (sfxr -> jsfxr / sfxr.me -> bfxr): jsfxr serializes an entire
synth patch into a base58 short-URL string like
`5EoyNVSymuxD8s7HP1ixqd...`, perfect for sharing, illegible on sight.
An agent driving such a tool produces exactly the rendering problem this SEP
addresses: the call is correct, compact, and opaque. `sfx_play` below models
that case with a simplified packed encoding (`patchcodec.py`).

## Run

```
pip install mcp jsonschema
python render_client.py     # spawns server.py over stdio automatically
```

## What it shows

| Tool | Case | Mechanism |
|---|---|---|
| `mix_set`  | flat schema, scalar args | tool-level `displayTemplate` |
| `mix_set`  | supplied arg the template doesn't reference | `[+N more args]` omission marker |
| `cue_ctl`  | `oneOf`-branched schema (play/stop/duck) | branch-scoped `displayTemplate` |
| `sfx_play` | dense packed patch string | raw fallback on call, `displayText` on result |

Sample output:

```
sfx_play {"patch": "00rg051o641jp"}   ->  play patch 00rg051o641jp
  result                              ->  square wave @ 988 Hz, 0.28 s
                                          envelope — coin-style pickup
```

The renderer (`render_client.py`) is the reference client behavior: literal
substitution, `...` for missing/non-scalar values, `{{`/`}}` escapes,
first-matching-branch tie-break, raw fallback everywhere else, and a
`[+N more args]` marker whenever a call supplies arguments the matched
template does not reference, so a partial template cannot quietly conceal
an argument (the call-side omission mitigation from the SEP's Security
Implications).

No SDK changes were needed, but the carrier matters. On SDK 1.x,
`ToolAnnotations` and `Annotations` passed unknown fields through on the
wire; SDK 2.x models silently strip them at both serialization ends, so
this PoC (ported to the 2.x lowlevel API) carries the tool-level template
and the result-side text in `_meta` under the extension-namespaced key
`io.modelcontextprotocol/display-templates`, per the Tool Annotations IG
extension draft, while branch-scoped templates ride inside the opaque
`inputSchema` dict, untouched by either SDK. The renderer checks `_meta`
first and falls back to annotation extras for 1.x-era servers. That the
reference SDK now makes annotation-borne experimentation impossible without
a spec change is itself part of the motivation for standardizing the field.
