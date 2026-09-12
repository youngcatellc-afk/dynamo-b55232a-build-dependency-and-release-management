"""Read a written depot back and work the reissue policy over it, independently.

This shares no code with the builder and none with the reference solution. It
reads the files off disk rather than the structures the builder held; it settles
paths by walking their components instead of calling the path library; it turns
an instant into a count of seconds with a calendar walk of its own rather than a
date library; it decides the embargo question in one pass over the log instead of
grouping rows by pressing;
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


def moment(written: str) -> int:
    """The instant a written timestamp names, as seconds since the epoch."""
    year, month, day = int(written[0:4]), int(written[5:7]), int(written[8:10])
    hour, minute, second = int(written[11:13]), int(written[14:16]), int(written[17:19])
    tail = written[19:]
    away = 0
    if tail and tail[0] in "+-":
        away = int(tail[1:3]) * 60 + int(tail[4:6])
        if tail[0] == "-":
            away = -away
    days = 0
    for step in range(1970, year):
        days += 366 if (step % 4 == 0 and step % 100 != 0) or step % 400 == 0 else 365
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    lengths = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    days += sum(lengths[: month - 1]) + day - 1
    return ((days * 24 + hour) * 60 + minute - away) * 60 + second


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
    cut = moment(book["cut"])
    floors = {row["outlet"]: moment(row["reissue_floor"]) for row in book["outlets"]}
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
        row["at"] = moment(row["sealed_at"])
        countersigned += 1 if short == 0 else 0
        pressings[row["pressing"]] = row
        shelf_rows.setdefault(row["outlet"], []).append(row)

    # One pass over the log: a pressing is shut if any row it owns is open at the
    # cut. Rows for a pressing may sit anywhere in the file and in any order.
    shut = set()
    for row in _read_lines(os.path.join(depot, "embargoes.jsonl")):
        if moment(row["opened_at"]) > cut:
            continue
        if row["released_at"] is not None and moment(row["released_at"]) <= cut:
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
            key=lambda row: (-row["revision"], -row["at"], row["pressing"]),
        )
        for row in contenders:
            if row["pressing"] in withdrawn:
                continue
            if row["at"] < floor or row["at"] > cut:
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
