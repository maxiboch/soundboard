"""Toy synth-patch codec, in the spirit of the sfxr family's share codes.

jsfxr (sfxr.me) famously serializes a full synth patch into a base58
short-URL string, a dense blob optimized for sharing, not reading. This
module implements a deliberately simplified stand-in: fixed-width base36
fields packed into one delimiter-free string, so the demo server can
actually decode what it plays while the string stays opaque to a human.

Layout (13 chars): wave(1) freq_hz(3) attack_ms(2) sustain_ms(2)
                   decay_ms(2) punch_pct(2) vol_pct(1)
"""

WAVES = ["square", "saw", "sine", "noise"]
_A = "0123456789abcdefghijklmnopqrstuvwxyz"


def _enc(n: int, width: int) -> str:
    s = ""
    while n:
        s = _A[n % 36] + s
        n //= 36
    return s.rjust(width, "0")


def _dec(s: str) -> int:
    return int(s, 36)


def encode(wave: str, freq_hz: int, attack_ms: int, sustain_ms: int,
           decay_ms: int, punch_pct: int, vol_pct: int) -> str:
    return (str(WAVES.index(wave)) + _enc(freq_hz, 3) + _enc(attack_ms, 2)
            + _enc(sustain_ms, 2) + _enc(decay_ms, 2) + _enc(punch_pct, 2)
            + _enc(vol_pct, 1))


def decode(patch: str) -> dict:
    return {
        "wave": WAVES[int(patch[0])],
        "freq_hz": _dec(patch[1:4]),
        "attack_ms": _dec(patch[4:6]),
        "sustain_ms": _dec(patch[6:8]),
        "decay_ms": _dec(patch[8:10]),
        "punch_pct": _dec(patch[10:12]),
        "vol_pct": _dec(patch[12]),
    }


def characterize(p: dict) -> str:
    """Heuristic sfxr-preset-style label for a decoded patch."""
    length_ms = p["attack_ms"] + p["sustain_ms"] + p["decay_ms"]
    if p["wave"] == "noise":
        return "explosion-style rumble" if p["decay_ms"] > 300 else "hit/hurt-style burst"
    if p["wave"] == "saw" and p["freq_hz"] > 600:
        return "laser-style zap"
    if p["freq_hz"] > 800 and length_ms < 400 and p["punch_pct"] > 30:
        return "coin-style pickup"
    if length_ms < 150:
        return "UI blip"
    return "tone"
