#!/usr/bin/env python3
"""Work the reissue policy over the depot and write the slate.

Five clauses decide whether a pressing is eligible for its outlet, and three
tie-breaks decide which of the eligible ones the outlet is owed. Several of them
turn on how the depot writes things down rather than on what it says:

  * a countersign names its subjects by content, not by pressing, so coverage is
    a question about the union of every release run rather than about any one of
    them; and paths and digests are compared as the file and the value they name,
    not as the strings they were written with;

  * the embargo log is append-only and unordered, so a pressing can carry several
    rows and it is shut at the cut if *any* of them was open then — reducing the
    log to one row per pressing quietly answers a different question;

  * a manifest is a list and not an index, so a path that appears twice has to be
    attested twice, and an instant is a moment rather than the text it was written
    with, so comparing the written forms puts some of them in the wrong order.

The strike list does double duty: it removes pressings, and the greatest version
it names on an outlet is the bar that outlet will not reissue back to.
"""

import json
import os
from datetime import datetime, timezone

DEPOT = "/app/depot"
ANSWER = "/app/reissue_slate.json"


def records(name):
    """Every JSON record in one line-delimited file of the depot."""
    with open(os.path.join(DEPOT, name), "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def denotes(spelling):
    """The file a path spelling names inside a pressing."""
    kept = []
    for piece in spelling.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if kept:
                kept.pop()
            continue
        kept.append(piece)
    return "/".join(kept)


def names(spelling):
    """The digest value a spelling names, whatever its case or prefix."""
    _, _, hexes = spelling.rpartition(":")
    return hexes.lower()


def ordering(version):
    """Versions are dotted numbers and order component by component."""
    return tuple(int(piece) for piece in version.split("."))


def instant(written):
    """The moment a timestamp names, whichever clock it was written against."""
    when = datetime.fromisoformat(written.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def main():
    with open(os.path.join(DEPOT, "outlets.json"), "r", encoding="utf-8") as handle:
        book = json.load(handle)
    cut = instant(book["cut"])
    floor = {row["outlet"]: instant(row["reissue_floor"]) for row in book["outlets"]}

    # Clause 5. Every release run contributes its subjects to one pool, and a
    # pressing is countersigned when every part of its manifest is in that pool.
    attested = set()
    for sign in records("countersigns.jsonl"):
        if sign["scope"] == "release":
            for subject in sign["subjects"]:
                attested.add((denotes(subject["path"]), names(subject["digest"])))

    pressings = list(records("pressings.jsonl"))
    covered = set()
    for pressing in pressings:
        if all((denotes(part["path"]), names(part["digest"])) in attested
               for part in pressing["parts"]):
            covered.add(pressing["pressing"])

    # Clause 4. Any row that was open at the cut shuts the pressing.
    shut = set()
    for row in records("embargoes.jsonl"):
        if instant(row["opened_at"]) <= cut:
            if row["released_at"] is None or instant(row["released_at"]) > cut:
                shut.add(row["pressing"])

    # Clauses 2 and 3, both off the strike list.
    version = {row["pressing"]: row["version"] for row in pressings}
    outlet_of = {row["pressing"]: row["outlet"] for row in pressings}
    struck = set()
    bar = {}
    for row in records("strikes.jsonl"):
        pid = row["pressing"]
        struck.add(pid)
        shelf = outlet_of[pid]
        here = ordering(version[pid])
        if shelf not in bar or here > bar[shelf]:
            bar[shelf] = here

    slate = {}
    for shelf in floor:
        eligible = []
        for pressing in pressings:
            pid = pressing["pressing"]
            if pressing["outlet"] != shelf or pid in struck or pid in shut:
                continue
            if not floor[shelf] <= instant(pressing["sealed_at"]) <= cut:
                continue
            if shelf in bar and ordering(pressing["version"]) <= bar[shelf]:
                continue
            if pid not in covered:
                continue
            eligible.append(pressing)
        if not eligible:
            continue
        best = min(eligible, key=lambda row: (-row["revision"],
                                              -instant(row["sealed_at"]).timestamp(),
                                              row["pressing"]))
        slate[shelf] = best["pressing"]

    with open(ANSWER, "w", encoding="utf-8") as handle:
        json.dump({"slate": slate, "countersigned": len(covered)}, handle,
                  indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
