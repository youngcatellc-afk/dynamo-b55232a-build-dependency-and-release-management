"""Read a written depot back and work the reissue policy over it, independently.

This shares no code with the builder and none with the reference solution. It
reads the files off disk rather than the structures the builder held; it settles
paths by walking their components instead of calling the path library; it keeps
instants as the text the depot wrote and compares them as text; it decides the
embargo question in one pass over the log instead of grouping rows by pressing;
and it walks each outlet in rank order and stops at the first pressing that holds
up, instead of filtering a field and then sorting it.

Two implementations that disagree mean the answer is one implementation's
opinion, so the grader refuses to grade until they agree.
"""

from __future__ import annotations

import json
import os


def settle_path(spelling: str) -> str:
    """Walk the components of a path spelling and say which file it names."""
    stack = []
    for piece in spelling.split("/"):
        if piece == "" or piece == ".":
            continue
        if piece == "..":
            if stack:
                stack.pop()
            continue
        stack.append(piece)
    return "/".join(stack)


def settle_digest(spelling: str) -> str:
    """The value a digest spelling names, whatever the case or the prefix."""
    return spelling.rpartition(":")[2].lower()


def release_order(text: str):
    return tuple(int(piece) for piece in text.split("."))


def _read_lines(path):
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def audit(depot: str) -> dict:
    """The slate this depot implies, and how many pressings are countersigned."""
    with open(os.path.join(depot, "outlets.json"), "r", encoding="utf-8") as handle:
        book = json.load(handle)
    cut = book["cut"]
    floors = {row["outlet"]: row["reissue_floor"] for row in book["outlets"]}
    shelves = [row["outlet"] for row in book["outlets"]]

    attested = set()
    for sign in _read_lines(os.path.join(depot, "countersigns.jsonl")):
        if sign["scope"] != "release":
            continue
        for subject in sign["subjects"]:
            attested.add((settle_path(subject["path"]), settle_digest(subject["digest"])))

    pressings = {}
    shelf_rows = {oid: [] for oid in shelves}
    countersigned = 0
    for row in _read_lines(os.path.join(depot, "pressings.jsonl")):
        short = 0
        for part in row["parts"]:
            if (settle_path(part["path"]), settle_digest(part["digest"])) not in attested:
                short += 1
        row["covered"] = short == 0
        countersigned += 1 if short == 0 else 0
        pressings[row["pressing"]] = row
        shelf_rows.setdefault(row["outlet"], []).append(row)

    # One pass over the log: a pressing is shut if any row it owns is open at the
    # cut. Rows for a pressing may sit anywhere in the file and in any order.
    shut = set()
    for row in _read_lines(os.path.join(depot, "embargoes.jsonl")):
        if row["opened_at"] > cut:
            continue
        if row["released_at"] is not None and row["released_at"] <= cut:
            continue
        shut.add(row["pressing"])

    # One pass over the strike list, which both removes pressings and raises the
    # version each outlet will not go back to.
    withdrawn = set()
    bar = {}
    for row in _read_lines(os.path.join(depot, "strikes.jsonl")):
        pid = row["pressing"]
        withdrawn.add(pid)
        oid = pressings[pid]["outlet"]
        here = release_order(pressings[pid]["version"])
        if oid not in bar or here > bar[oid]:
            bar[oid] = here

    slate = {}
    for oid in shelves:
        floor = floors[oid]
        contenders = sorted(
            shelf_rows.get(oid, []),
            key=lambda row: (-row["revision"], _reverse(row["sealed_at"]), row["pressing"]),
        )
        for row in contenders:
            if row["pressing"] in withdrawn:
                continue
            if row["sealed_at"] < floor or row["sealed_at"] > cut:
                continue
            if oid in bar and release_order(row["version"]) <= bar[oid]:
                continue
            if row["pressing"] in shut:
                continue
            if not row["covered"]:
                continue
            slate[oid] = row["pressing"]
            break

    return {"slate": slate, "countersigned": countersigned}


def _reverse(text: str):
    """Sort an instant written as text into descending order."""
    return tuple(-ord(ch) for ch in text)
