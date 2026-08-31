#!/usr/bin/env python3
"""
OrcaSlicer post-processing script: per-object Z-offset sweep.

Reads the object name Orca emits in EXCLUDE_OBJECT_START markers, pulls the
Z-offset out of the STL filename, and injects a Klipper SET_GCODE_OFFSET so
each frame on the plate prints at its own offset.

Naming contract - the STL filename carries the value:
    Z-Offset-Test-pos-0.040.stl  ->  Z = +0.040
    Z-Offset-Test-neg-0.060.stl  ->  Z = -0.060

The embossed label and the applied offset therefore come from one source,
so they cannot drift apart.

MOVE=1 is not optional. Without it SET_GCODE_OFFSET only updates base_position,
and the toolhead does not physically move until the next command carrying a Z
word - which mid-layer is the *next layer change*. Every frame on layer 1 would
print at the same height while the labels claimed otherwise.

Usage (Orca -> Others -> Post-processing Scripts):
    /usr/bin/python3 /path/to/zoffset-sweep-postprocess.py;
Orca appends the gcode path and expects the file rewritten in place.
"""

import re
import sys

NAME_RE = re.compile(r"EXCLUDE_OBJECT_START\s+NAME=(\S+)")
VALUE_RE = re.compile(r"(pos|neg)-(\d+\.\d+)")

MOVE_SPEED = 5.0


def offset_from_name(name):
    """Return the signed offset encoded in an object name, or None."""
    m = VALUE_RE.search(name)
    if not m:
        return None
    sign, magnitude = m.groups()
    value = float(magnitude)
    return -value if sign == "neg" else value


def main():
    if len(sys.argv) < 2:
        sys.exit("error: no gcode file given (Orca passes it as the last arg)")
    path = sys.argv[-1]

    with open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
        lines = fh.readlines()

    out = []
    applied = None          # offset currently in effect
    injections = 0
    seen = {}               # value -> object name, for the summary
    last_end = None         # index in `out` of the final EXCLUDE_OBJECT_END

    for line in lines:
        out.append(line)

        if line.startswith("EXCLUDE_OBJECT_END"):
            last_end = len(out)
            continue

        m = NAME_RE.match(line)
        if not m:
            continue

        value = offset_from_name(m.group(1))
        if value is None:
            continue

        seen.setdefault(value, m.group(1))

        # Re-applying an unchanged offset would emit a zero-length move.
        if applied is not None and abs(value - applied) < 1e-9:
            continue

        out.append(
            "SET_GCODE_OFFSET Z=%.3f MOVE=1 MOVE_SPEED=%.1f "
            "; zoffset-sweep\n" % (value, MOVE_SPEED)
        )
        applied = value
        injections += 1

    if injections == 0:
        sys.exit(
            "error: no per-object Z-offsets injected.\n"
            "  Either object labelling is off (Orca: enable 'Exclude objects'),\n"
            "  or no STL name matched the pos-/neg-0.000 contract."
        )

    # Leave the machine at a clean offset rather than the last frame's.
    reset = "SET_GCODE_OFFSET Z=0 MOVE=0 ; zoffset-sweep reset\n"
    if last_end is not None:
        out.insert(last_end, reset)
    else:
        out.append(reset)

    with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.writelines(out)

    values = sorted(seen)
    sys.stderr.write(
        "zoffset-sweep: %d objects, %d injections, range %+.3f to %+.3f\n"
        % (len(values), injections, values[0], values[-1])
    )


if __name__ == "__main__":
    main()
