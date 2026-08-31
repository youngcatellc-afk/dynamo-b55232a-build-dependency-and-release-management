"""What the grader stands on: a depot of its own, and the file the agent left.

Nothing under /app is ever treated as the truth. The depot is rebuilt from the
fixture sources into a directory the grader makes for itself, and the answer is
taken from there. It is derived twice — once by the builder from the structures it
built, once by a separate reader that re-parses the written files — and the two
have to agree before a single assertion runs. Every misreading of the policy on
the board has to change a graded value on that depot, so no clause of the policy
can be dead on the data that ships.

The only path opened under /app is the deliverable the instruction names, plus the
depot files, which are read to confirm they were left alone and never to decide
what the right answer is.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture")
SLATE_PATH = "/app/reissue_slate.json"
DEPOT_PATH = "/app/depot"
SLATE_CEILING = 512 * 1024
KEYS = ("countersigned", "slate")

_ground = None


def _load(alias, filename):
    spot = importlib.util.spec_from_file_location(alias, os.path.join(FIXTURE, filename))
    module = importlib.util.module_from_spec(spot)
    sys.modules[alias] = module
    spot.loader.exec_module(module)
    return module


def _sweep(root):
    """Every file under a tree, as relative path to SHA-256 of its bytes."""
    seal = {}
    for here, folders, files in os.walk(root):
        folders.sort()
        for name in sorted(files):
            full = os.path.join(here, name)
            with open(full, "rb") as handle:
                seal[os.path.relpath(full, root).replace(os.sep, "/")] = \
                    hashlib.sha256(handle.read()).hexdigest()
    return seal


def ground():
    """Rebuild the depot out of reach, read it back twice, and keep the answer."""
    global _ground
    if _ground is not None:
        return _ground
    builder = _load("_depot_builder", "forge.py")
    reader = _load("_depot_reader", "sift.py")
    with tempfile.TemporaryDirectory() as scratch:
        made = builder.build(scratch)
        depot = os.path.join(scratch, "depot")
        reread = reader.audit(depot)
        seal = _sweep(depot)
        home = {}
        with open(os.path.join(depot, "pressings.jsonl"), "r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    home[row["pressing"]] = row["outlet"]
    if reread != made["answer"]:
        raise AssertionError("the two readings of the rebuilt depot disagree")
    if len(made["board"]) != len(builder.READINGS):
        raise AssertionError("a reading of the policy went missing from the board")
    for name, bent in made["board"].items():
        if bent == made["answer"]:
            raise AssertionError("reading %s decides nothing on this depot" % name)
    _ground = {
        "answer": made["answer"],
        "board": sorted(made["board"]),
        "counts": made["counts"],
        "seal": seal,
        "outlets": [row[0] for row in builder.OUTLETS],
        "home": home,
    }
    return _ground


def shipped_seal():
    """The same sweep over the copy of the depot the agent was given."""
    if not os.path.isdir(DEPOT_PATH):
        return None
    return _sweep(DEPOT_PATH)


def submitted():
    """Read the slate, refusing to follow a symlink planted at that path."""
    try:
        handle = os.open(SLATE_PATH, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {"complaint": SLATE_PATH + " was never written"}
    except OSError as trouble:
        return {"complaint": "%s could not be opened: %s" % (SLATE_PATH, trouble)}
    try:
        if os.fstat(handle).st_size > SLATE_CEILING:
            os.close(handle)
            return {"complaint": SLATE_PATH + " is implausibly large"}
        with os.fdopen(handle, "r", encoding="utf-8") as stream:
            text = stream.read()
    except OSError as trouble:
        return {"complaint": "%s could not be read: %s" % (SLATE_PATH, trouble)}
    except UnicodeDecodeError as trouble:
        return {"complaint": "%s is not UTF-8: %s" % (SLATE_PATH, trouble)}
    try:
        return {"body": json.loads(text)}
    except json.JSONDecodeError as trouble:
        return {"complaint": "%s is not valid JSON: %s" % (SLATE_PATH, trouble)}


def plain_text(value):
    """True for a JSON string, and for nothing else."""
    return isinstance(value, str)


def whole_number(value):
    """True for a JSON integer, and for nothing that merely looks like one."""
    return isinstance(value, int) and not isinstance(value, bool)
