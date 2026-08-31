"""Build the release depot, and say — from the structures it built — what the slate is.

Everything here is a pure function of one 64-bit seed. The generator is a linear
congruential sequence written out in full rather than `random`, because the stdlib
generator is not promised to be stable between CPython releases and the depot has
to come out byte-identical on every machine that rebuilds it. No clock, no locale,
no network, no unseeded entropy.

The depot is built clean first and the fixtures are planted afterwards, one at a
time. A fixture is kept only once the slate has been recomputed under the reading
it exists to punish and the two answers have been shown to differ, so no placement
here depends on happening to land somewhere that matters.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath

# The instant the signing key was withdrawn. Everything in the depot is dated
# against it; nothing is dated against the wall clock.
CUT = 1932627600  # 2031-04-17T09:00:00Z

SEED = 0x5C7A19E3B44D0F21

DAY = 86400
HOUR = 3600

OUTLETS = [
    ("ot-01", "northshelf"),
    ("ot-02", "harbourgate"),
    ("ot-03", "quarryside"),
    ("ot-04", "moorgate"),
    ("ot-05", "linnetfield"),
    ("ot-06", "kilnside"),
    ("ot-07", "tarnwick"),
    ("ot-08", "penfold"),
    ("ot-09", "beaconhill"),
    ("ot-10", "saltmere"),
    ("ot-11", "colliers"),
    ("ot-12", "wrayford"),
    ("ot-13", "estbury"),
    ("ot-14", "downlea"),
]

# Outlet ot-14 is the one with nothing to reissue. Its in-window pressings were
# never countersigned at all, which no misreading of the policy turns around.
BARREN = "ot-14"

# Outlet ot-06 has never had to withdraw a pressing, so it carries no strike and
# therefore no version bar.
UNBARRED = "ot-06"

CORE_PARTS = [
    "boot/loader.efi",
    "firmware/core.bin",
    "firmware/radio.bin",
    "etc/defaults.conf",
]

OPTIONAL_PARTS = [
    "lib/libradio.so",
    "lib/libpower.so",
    "lib/libsensor.so",
    "lib/libtelemetry.so",
    "bin/provision",
    "bin/selftest",
    "bin/recover",
    "share/locale/en.mo",
    "share/locale/de.mo",
    "share/locale/ja.mo",
    "share/tables/rf.tbl",
    "share/tables/thermal.tbl",
    "modules/can.ko",
    "modules/lin.ko",
    "modules/usbnet.ko",
    "doc/release-notes.txt",
]

# Two files that do not change between pressings, so their digests recur.
STABLE_PARTS = ["etc/keys/root.pub", "etc/keys/update.pub"]

BUILDERS = ["forge-a", "forge-b", "forge-c", "quay-north", "quay-south", "outpost"]

# Every reading of the policy the board tries. Truth is all of them off. Each one
# is a coherent way to read the depot that a careful engineer could land on, and
# each has to change a graded value on the depot that ships.
READINGS = (
    "raw_path",        # compare path spellings as written
    "raw_digest",      # compare digest spellings as written
    "path_only",       # a subject covers a part when the path matches
    "one_sign",        # one countersign has to cover the whole manifest
    "any_scope",       # count countersigns of every scope
    "embargo_last",    # one embargo row per pressing, the last written
    "embargo_first",   # one embargo row per pressing, the first written
    "released_ge",     # a release landing on the cut still leaves it open
    "opened_strict",   # an embargo opened on the cut is not yet open
    "floor_strict",    # sealed strictly after the floor
    "cut_strict",      # sealed strictly before the cut
    "no_cut",          # no upper bound on the sealing instant
    "keep_struck",     # the strike list is not read at all
    "no_bar",          # struck pressings drop out but set no version bar
    "bar_inclusive",   # a version equal to the bar clears it
    "lex_version",     # order versions as text
    "pick_latest",     # pick the latest sealing rather than the highest revision
    "id_tiebreak",     # settle a revision tie on the identifier alone
    "id_desc",         # settle the last tie on the largest identifier
)


class Roll:
    """The pinned generator: a 64-bit LCG, high bits only, and nothing else."""

    __slots__ = ("state",)

    MASK = (1 << 64) - 1

    def __init__(self, seed: int) -> None:
        self.state = seed & self.MASK

    def _step(self) -> int:
        self.state = (self.state * 6364136223846793005 + 1442695040888963407) & self.MASK
        return self.state >> 17

    def below(self, bound: int) -> int:
        return self._step() % bound

    def between(self, low: int, high: int) -> int:
        return low + self.below(high - low + 1)

    def pick(self, items):
        return items[self.below(len(items))]

    def shuffled(self, items):
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.below(i + 1)
            out[i], out[j] = out[j], out[i]
        return out

    def sample(self, items, count):
        return self.shuffled(items)[:count]


def stamp(seconds: int) -> str:
    """An instant as the depot writes it: UTC, second resolution, trailing Z."""
    days, rest = divmod(seconds, DAY)
    hh, rest = divmod(rest, HOUR)
    mm, ss = divmod(rest, 60)
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    year = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + 3 if mp < 10 else mp - 9
    if month <= 2:
        year += 1
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (year, month, day, hh, mm, ss)


def digest_of(*bits) -> str:
    """A stand-in for the SHA-256 of a file's bytes, stable and unguessable."""
    body = "|".join(str(b) for b in ("depot", SEED) + bits)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def tidy_path(text: str) -> str:
    """The path a spelling denotes inside a pressing."""
    settled = posixpath.normpath(text)
    return settled[2:] if settled.startswith("./") else settled


def tidy_digest(text: str) -> str:
    """The value a digest spelling names."""
    return text.split(":")[-1].lower()


def version_key(text: str):
    return tuple(int(part) for part in text.split("."))


def _flip(text: str):
    """A sort key that puts the largest identifier first."""
    return tuple(-ord(ch) for ch in text)


# --------------------------------------------------------------------------
# the policy
# --------------------------------------------------------------------------

def resolve(state: dict, reading=()) -> dict:
    """Work the reissue policy over the built structures under one reading."""
    flag = set(reading)

    subjects = set()
    per_sign = []
    for sign in state["countersigns"]:
        if "any_scope" not in flag and sign["scope"] != "release":
            continue
        here = set()
        for subject in sign["subjects"]:
            path = subject["path"] if "raw_path" in flag else tidy_path(subject["path"])
            if "path_only" in flag:
                here.add(path)
            else:
                dig = (subject["digest"] if "raw_digest" in flag
                       else tidy_digest(subject["digest"]))
                here.add((path, dig))
        subjects |= here
        per_sign.append(here)

    def keys_of(pressing):
        out = []
        for part in pressing["parts"]:
            path = part["path"] if "raw_path" in flag else tidy_path(part["path"])
            if "path_only" in flag:
                out.append(path)
            else:
                dig = part["digest"] if "raw_digest" in flag else tidy_digest(part["digest"])
                out.append((path, dig))
        return out

    covered = {}
    for pressing in state["pressings"]:
        keys = keys_of(pressing)
        if "one_sign" in flag:
            covered[pressing["pressing"]] = any(
                all(key in here for key in keys) for here in per_sign
            )
        else:
            covered[pressing["pressing"]] = all(key in subjects for key in keys)

    struck = {row["pressing"] for row in state["strikes"]}

    logged = {}
    for row in state["embargoes"]:
        logged.setdefault(row["pressing"], []).append(row)

    def embargoed(pid):
        rows = logged.get(pid, [])
        if not rows:
            return False
        if "embargo_last" in flag:
            rows = rows[-1:]
        elif "embargo_first" in flag:
            rows = rows[:1]
        for row in rows:
            if "opened_strict" in flag:
                if row["opened_at"] >= CUT:
                    continue
            elif row["opened_at"] > CUT:
                continue
            if row["released_at"] is None:
                return True
            if "released_ge" in flag:
                if row["released_at"] >= CUT:
                    return True
            elif row["released_at"] > CUT:
                return True
        return False

    by_outlet = {}
    for pressing in state["pressings"]:
        by_outlet.setdefault(pressing["outlet"], []).append(pressing)

    slate = {}
    field_of = {}
    for outlet in state["outlets"]:
        oid = outlet["outlet"]
        floor = outlet["reissue_floor"]
        here = by_outlet.get(oid, [])

        bar = None
        if not ("keep_struck" in flag or "no_bar" in flag):
            for pressing in here:
                if pressing["pressing"] not in struck:
                    continue
                key = (pressing["version"] if "lex_version" in flag
                       else version_key(pressing["version"]))
                if bar is None or key > bar:
                    bar = key

        field = []
        for pressing in here:
            pid = pressing["pressing"]
            if "keep_struck" not in flag and pid in struck:
                continue
            if "floor_strict" in flag:
                if pressing["sealed_at"] <= floor:
                    continue
            elif pressing["sealed_at"] < floor:
                continue
            if "cut_strict" in flag:
                if pressing["sealed_at"] >= CUT:
                    continue
            elif "no_cut" not in flag and pressing["sealed_at"] > CUT:
                continue
            if bar is not None:
                key = (pressing["version"] if "lex_version" in flag
                       else version_key(pressing["version"]))
                if "bar_inclusive" in flag:
                    if key < bar:
                        continue
                elif key <= bar:
                    continue
            if embargoed(pid):
                continue
            if not covered[pid]:
                continue
            field.append(pressing)

        if "pick_latest" in flag:
            rank = lambda p: (-p["sealed_at"], p["pressing"])
        elif "id_tiebreak" in flag:
            rank = lambda p: (-p["revision"], p["pressing"])
        elif "id_desc" in flag:
            rank = lambda p: (-p["revision"], -p["sealed_at"], _flip(p["pressing"]))
        else:
            rank = lambda p: (-p["revision"], -p["sealed_at"], p["pressing"])
        order = sorted(field, key=rank)
        field_of[oid] = [p["pressing"] for p in order]
        if order:
            slate[oid] = order[0]["pressing"]

    return {
        "slate": slate,
        "countersigned": sum(1 for value in covered.values() if value),
        "field": field_of,
    }


def graded(answer: dict) -> dict:
    """Just the part of a resolution the slate is graded on."""
    return {"slate": answer["slate"], "countersigned": answer["countersigned"]}


# --------------------------------------------------------------------------
# building the depot
# --------------------------------------------------------------------------

class Pool:
    """Identifiers dealt from a shuffled pool, so id order says nothing about time."""

    __slots__ = ("items", "at")

    def __init__(self, items):
        self.items = items
        self.at = 0

    def take(self):
        value = self.items[self.at]
        self.at += 1
        return value


def _lay_out(roll: Roll) -> dict:
    """The clean depot: pressings, manifests, countersigns, embargoes, strikes."""
    press_pool = Pool(roll.shuffled(["pr-%04d" % n for n in range(1, 1400)]))
    sign_pool = Pool(roll.shuffled(["cs-%04d" % n for n in range(1, 3400)]))
    hold_pool = Pool(roll.shuffled(["eb-%04d" % n for n in range(1, 700)]))
    strike_pool = Pool(roll.shuffled(["st-%04d" % n for n in range(1, 700)]))
    take_id = press_pool.take
    take_sign = sign_pool.take
    take_hold = hold_pool.take
    take_strike = strike_pool.take

    outlets = []
    pressings = []
    stable_digest = {}

    for oid, name in OUTLETS:
        floor = CUT - DAY * roll.between(210, 520)
        outlets.append({
            "outlet": oid,
            "name": name,
            "reissue_floor": floor,
            "family": roll.pick(["cortex", "meridian", "halyard", "pennine"]),
        })
        for path in STABLE_PARTS:
            stable_digest[(oid, path)] = digest_of("stable", oid, path)

        count = roll.between(58, 78)
        opened = CUT - DAY * roll.between(880, 1010)
        closed = CUT + DAY * roll.between(25, 80)
        run = closed - opened
        major = 1
        minor = roll.between(2, 4)
        patch = 0
        for index in range(count):
            cursor = (opened + (run * (index + 1)) // count
                      + HOUR * roll.between(0, 20) + 60 * roll.between(0, 59))
            patch += roll.between(1, 3)
            if patch > 9:
                minor += 1
                patch = roll.between(0, 2)
            if minor > 9:
                major += 1
                minor = 0
            version = "%d.%d.%d" % (major, minor, patch)
            chosen = [path for path in STABLE_PARTS if roll.below(4)]
            chosen += CORE_PARTS
            chosen += roll.sample(OPTIONAL_PARTS, roll.between(2, 11))
            pid = take_id()
            parts = []
            for path in sorted(set(chosen)):
                if path in STABLE_PARTS:
                    dig = stable_digest[(oid, path)]
                else:
                    dig = digest_of("part", pid, path)
                parts.append({
                    "path": path,
                    "digest": dig,
                    "bytes": 512 * roll.between(3, 900),
                })
            pressings.append({
                "pressing": pid,
                "outlet": oid,
                "version": version,
                "revision": roll.between(1, 40),
                "sealed_at": cursor,
                "line": roll.pick(BUILDERS),
                "parts": parts,
            })

    # Countersigns. Most pressings are attested in full, over one to three runs;
    # a few are attested only in part, and a few only from a staging run.
    countersigns = []
    for pressing in pressings:
        parts = list(pressing["parts"])
        if pressing["outlet"] == BARREN and pressing["sealed_at"] >= CUT - DAY * 700:
            mode = "none"
        else:
            draw = roll.below(100)
            if draw < 86:
                mode = "full"
            elif draw < 92:
                mode = "short"
            elif draw < 97:
                mode = "staging"
            else:
                mode = "none"
        if mode == "none":
            continue
        if mode == "short":
            parts = parts[:-1]
            if not parts:
                continue
        chunks = min(roll.between(1, 3), len(parts))
        order = roll.shuffled(parts)
        buckets = [[] for _ in range(chunks)]
        for slot, part in enumerate(order):
            buckets[slot % chunks].append(part)
        for bucket in buckets:
            if not bucket:
                continue
            countersigns.append({
                "countersign": take_sign(),
                "builder": roll.pick(BUILDERS),
                "issued_at": pressing["sealed_at"] + HOUR * roll.between(1, 60),
                "scope": "staging" if mode == "staging" else "release",
                "subjects": [{"path": p["path"], "digest": p["digest"]} for p in bucket],
            })

    # Strikes. Every outlet withdraws a handful of pressings over its life. They
    # are drawn from the older part of each run, which is what keeps the version
    # bar an ordinary working constraint rather than a wall.
    strikes = []
    for oid, _ in OUTLETS:
        if oid == UNBARRED:
            continue
        here = [p for p in pressings if p["outlet"] == oid]
        here.sort(key=lambda p: p["sealed_at"])
        early = here[: (len(here) * 72) // 100]
        for pressing in roll.sample(early, roll.between(5, 11)):
            strikes.append({
                "strike": take_strike(),
                "pressing": pressing["pressing"],
                "struck_at": pressing["sealed_at"] + DAY * roll.between(2, 90),
                "reason": roll.pick(["regression", "signing", "supply", "field-report"]),
            })

    # Embargoes. An append-only log: a pressing can carry several rows.
    embargoes = []
    for pressing in roll.sample(pressings, len(pressings) // 6):
        rounds = 1 if roll.below(3) else roll.between(2, 3)
        opened = pressing["sealed_at"] + DAY * roll.between(1, 40)
        for _ in range(rounds):
            shut = None if roll.below(5) == 0 else opened + DAY * roll.between(2, 120)
            embargoes.append({
                "embargo": take_hold(),
                "pressing": pressing["pressing"],
                "opened_at": opened,
                "released_at": shut,
                "raised_by": roll.pick(["quality", "legal", "security", "supply"]),
            })
            if shut is None:
                break
            opened = shut + DAY * roll.between(3, 60)

    return {
        "outlets": outlets,
        "pressings": pressings,
        "countersigns": countersigns,
        "embargoes": embargoes,
        "strikes": strikes,
        "pools": {
            "countersign": sign_pool,
            "embargo": hold_pool,
            "strike": strike_pool,
        },
    }


# --------------------------------------------------------------------------
# planting the fixtures
# --------------------------------------------------------------------------

_BENT = {"path": 0, "digest": 0}


def _bend_path(path: str) -> str:
    """A second spelling of the same path inside the pressing."""
    head, _, tail = path.rpartition("/")
    _BENT["path"] += 1
    choice = _BENT["path"] % 3
    if choice == 0 or not head:
        return "./" + path
    if choice == 1:
        return head + "//" + tail
    return head + "/./" + tail


def _bend_digest(digest: str) -> str:
    """A second spelling of the same digest value."""
    _BENT["digest"] += 1
    return "sha256:" + digest if _BENT["digest"] % 2 else digest.upper()


def _find(state, pid):
    for pressing in state["pressings"]:
        if pressing["pressing"] == pid:
            return pressing
    raise KeyError(pid)


def _outlet(state, oid):
    for outlet in state["outlets"]:
        if outlet["outlet"] == oid:
            return outlet
    raise KeyError(oid)


def _here(state, oid):
    rows = [p for p in state["pressings"] if p["outlet"] == oid]
    rows.sort(key=lambda p: p["sealed_at"])
    return rows


def _field(state, oid):
    order = resolve(state)["field"].get(oid, [])
    return [_find(state, pid) for pid in order]


def _bar(state, oid):
    struck = {row["pressing"] for row in state["strikes"]}
    best = None
    for pressing in _here(state, oid):
        if pressing["pressing"] not in struck:
            continue
        key = version_key(pressing["version"])
        if best is None or key > best:
            best = key
    return best


def _above(bar, step=2):
    """The next version clear of the bar, keeping every component to one digit."""
    if bar is None:
        return "2.0.0"
    if bar[1] + step <= 9:
        return "%d.%d.%d" % (bar[0], bar[1] + step, 0)
    return "%d.0.0" % (bar[0] + 1)


def _unstrike(state, pid):
    state["strikes"] = [row for row in state["strikes"] if row["pressing"] != pid]


def _clear_embargoes(state, pid):
    state["embargoes"] = [row for row in state["embargoes"] if row["pressing"] != pid]


def _sign_all(state, pools, pressing, scope="release", chunks=1):
    """Attest every part of a pressing, over `chunks` countersigns."""
    parts = list(pressing["parts"])
    chunks = max(1, min(chunks, len(parts)))
    buckets = [[] for _ in range(chunks)]
    for slot, part in enumerate(parts):
        buckets[slot % chunks].append(part)
    for bucket in buckets:
        state["countersigns"].append({
            "countersign": pools["countersign"].take(),
            "builder": "forge-a",
            "issued_at": pressing["sealed_at"] + HOUR * 6,
            "scope": scope,
            "subjects": [{"path": p["path"], "digest": p["digest"]} for p in bucket],
        })


def _detach(pressing):
    """Give this pressing's parts digests no other pressing shares, and no cover."""
    for part in pressing["parts"]:
        part["digest"] = digest_of("plant", pressing["pressing"], part["path"])


def _promote(state, pools, roll, oid, pressing, revision, version=None,
             chunks=1, scope="release", window=True):
    """Make one pressing an outright candidate at the revision asked for."""
    outlet = _outlet(state, oid)
    _unstrike(state, pressing["pressing"])
    _clear_embargoes(state, pressing["pressing"])
    _detach(pressing)
    pressing["revision"] = revision
    pressing["version"] = version if version else _above(_bar(state, oid))
    if window and not (outlet["reissue_floor"] <= pressing["sealed_at"] <= CUT):
        pressing["sealed_at"] = outlet["reissue_floor"] + DAY * roll.between(20, 60)
    _sign_all(state, pools, pressing, scope=scope, chunks=chunks)
    return pressing


def _spare(state, oid, used, want=1):
    """Unclaimed pressings on this outlet that already sit inside its window."""
    floor = _outlet(state, oid)["reissue_floor"]
    out = []
    for pressing in reversed(_here(state, oid)):
        if pressing["pressing"] in used:
            continue
        if not floor <= pressing["sealed_at"] <= CUT:
            continue
        out.append(pressing)
        used = set(used) | {pressing["pressing"]}
        if len(out) == want:
            break
    if len(out) < want:
        raise AssertionError("outlet %s has no spare pressing to plant on" % oid)
    return out


def _row_embargo(pools, pid, opened, released, raised="quality"):
    return {
        "embargo": pools["embargo"].take(),
        "pressing": pid,
        "opened_at": opened,
        "released_at": released,
        "raised_by": raised,
    }


def _respell_subject(state, part, path=None, digest=None):
    """Write one attested subject a second way, leaving the value it names alone."""
    hits = 0
    for sign in state["countersigns"]:
        for subject in sign["subjects"]:
            if subject["path"] == part["path"] and subject["digest"] == part["digest"]:
                if path is not None:
                    subject["path"] = path
                if digest is not None:
                    subject["digest"] = digest
                hits += 1
    if hits != 1:
        raise AssertionError("expected one subject to respell, found %d" % hits)


def _restale(state, part, stale):
    """Leave the subject naming this path, but naming a superseded digest."""
    hits = 0
    for sign in state["countersigns"]:
        for subject in sign["subjects"]:
            if subject["path"] == part["path"] and subject["digest"] == part["digest"]:
                subject["digest"] = stale
                hits += 1
    if hits != 1:
        raise AssertionError("expected one subject to stale, found %d" % hits)


def _plain(path):
    return path not in STABLE_PARTS


def _plant(state, roll, pools):
    """Put every fixture in place. The caller then proves each one decisive."""
    order_marks = []

    # ot-01 -- the winner spells one manifest path a second way, and was sealed
    # on the cut itself.
    oid = "ot-01"
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"])
    lead["sealed_at"] = CUT
    bendable = [p for p in lead["parts"] if _plain(p["path"])]
    bendable[1]["path"] = _bend_path(bendable[1]["path"])

    # ot-02 -- one attested digest is written a second way, and a pressing sealed
    # after the cut would lead if the cut were not a bound.
    oid = "ot-02"
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"])
    mark = [p for p in lead["parts"] if _plain(p["path"])][0]
    _respell_subject(state, mark, digest=_bend_digest(mark["digest"]))
    late = _spare(state, oid, {lead["pressing"]})[0]
    _promote(state, pools, roll, oid, late, lead["revision"] + 3, window=False)
    late["sealed_at"] = CUT + DAY * roll.between(6, 30)

    # ot-03 -- the winner is attested only by two runs together, one manifest
    # digest is written a second way, and one subject path is too.
    oid = "ot-03"
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"], chunks=2)
    plain = [p for p in lead["parts"] if _plain(p["path"])]
    plain[0]["digest"] = _bend_digest(plain[0]["digest"])
    _respell_subject(state, plain[2], path=_bend_path(plain[2]["path"]))

    # ot-04 -- a higher-revision pressing whose subject names the right path but
    # a superseded digest.
    oid = "ot-04"
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"])
    lure = _spare(state, oid, {lead["pressing"]})[0]
    _promote(state, pools, roll, oid, lure, lead["revision"] + 2)
    part = [p for p in lure["parts"] if _plain(p["path"])][0]
    _restale(state, part, digest_of("superseded", lure["pressing"], part["path"]))

    # ot-05 / ot-06 -- an append-only embargo log where one row is still open and
    # another, for the same pressing, was released long ago.
    for oid, where in (("ot-05", "last"), ("ot-06", "first")):
        top = _field(state, oid)
        lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"])
        lure = _spare(state, oid, {lead["pressing"]})[0]
        _promote(state, pools, roll, oid, lure, lead["revision"] + 2)
        still = _row_embargo(pools, lure["pressing"], CUT - DAY * 34, None, "security")
        done = _row_embargo(pools, lure["pressing"], CUT - DAY * 260,
                            CUT - DAY * 190, "supply")
        pair = [still, done] if where == "last" else [done, still]
        state["embargoes"].extend(pair)
        order_marks.append([row["embargo"] for row in pair])

    # ot-07 -- an embargo released on the cut instant, so the pressing is free.
    oid = "ot-07"
    top = _field(state, oid)
    lead = top[0]
    lure = _spare(state, oid, {lead["pressing"]})[0]
    _promote(state, pools, roll, oid, lure, lead["revision"] + 2)
    state["embargoes"].append(
        _row_embargo(pools, lure["pressing"], CUT - DAY * 55, CUT, "legal"))

    # ot-08 -- the winner was sealed on the reissue floor itself.
    oid = "ot-08"
    top = _field(state, oid)
    lead = top[0]
    lure = _spare(state, oid, {lead["pressing"]})[0]
    _promote(state, pools, roll, oid, lure, lead["revision"] + 2)
    lure["sealed_at"] = _outlet(state, oid)["reissue_floor"]

    # ot-09 -- the bar and the winner straddle the point where a minor number
    # gains a digit.
    oid = "ot-09"
    floor = _outlet(state, oid)["reissue_floor"]
    struck = {row["pressing"] for row in state["strikes"]}
    for pressing in _here(state, oid):
        if pressing["pressing"] in struck:
            pressing["version"] = "1.%d.%d" % (roll.between(2, 8), roll.between(0, 9))
        elif pressing["sealed_at"] >= floor:
            pressing["version"] = "1.%d.%d" % (roll.between(10, 16), roll.between(0, 9))
    peak = [p for p in _here(state, oid) if p["pressing"] in struck][-1]
    peak["version"] = "1.9.14"
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"], version="1.10.2")
    runner = _spare(state, oid, {lead["pressing"]})[0]
    _promote(state, pools, roll, oid, runner, lead["revision"] - 1, version="1.9.19")

    # ot-10 -- one pressing sits exactly on the bar and one sits just under it.
    oid = "ot-10"
    bar = _bar(state, oid)
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"])
    used = {lead["pressing"]}
    level, under = _spare(state, oid, used, want=2)
    _promote(state, pools, roll, oid, level, lead["revision"] + 2,
             version="%d.%d.%d" % bar)
    step = (bar[0], bar[1], bar[2] - 1) if bar[2] else (bar[0], bar[1] - 1, 7)
    _promote(state, pools, roll, oid, under, lead["revision"] + 4,
             version="%d.%d.%d" % step)

    # ot-11 -- one higher-revision pressing attested only from a staging run, and
    # another under an embargo opened on the cut instant.
    oid = "ot-11"
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"])
    staged, held = _spare(state, oid, {lead["pressing"]}, want=2)
    _promote(state, pools, roll, oid, staged, lead["revision"] + 2, scope="staging")
    _promote(state, pools, roll, oid, held, lead["revision"] + 4)
    state["embargoes"].append(
        _row_embargo(pools, held["pressing"], CUT, None, "quality"))

    # ot-12 -- the highest-revision pressing on the outlet was struck.
    oid = "ot-12"
    bar = _bar(state, oid)
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], top[0]["revision"])
    gone = _spare(state, oid, {lead["pressing"]})[0]
    step = (bar[0], bar[1], bar[2] - 1) if bar[2] else (bar[0], bar[1] - 1, 6)
    _promote(state, pools, roll, oid, gone, lead["revision"] + 2,
             version="%d.%d.%d" % step)
    state["strikes"].append({
        "strike": pools["strike"].take(),
        "pressing": gone["pressing"],
        "struck_at": gone["sealed_at"] + DAY * 11,
        "reason": "regression",
    })

    # ot-13 -- three pressings share the top revision and two of them share the
    # sealing instant, so every tie-break in turn decides the outlet.
    oid = "ot-13"
    top = _field(state, oid)
    lead = _promote(state, pools, roll, oid, top[0], 39)
    for pressing in _here(state, oid):
        if pressing["pressing"] != lead["pressing"] and pressing["revision"] > 30:
            pressing["revision"] = roll.between(6, 30)
    pool = [p for p in _here(state, oid) if p["pressing"] != lead["pressing"]]
    lower = [p for p in pool if p["pressing"] < lead["pressing"]]
    upper = [p for p in pool if p["pressing"] > lead["pressing"]]
    early = _promote(state, pools, roll, oid, lower[-1], 39)
    early["sealed_at"] = lead["sealed_at"] - DAY * 3
    twin = _promote(state, pools, roll, oid, upper[-1], 39)
    twin["sealed_at"] = lead["sealed_at"]
    trail = _promote(state, pools, roll, oid, upper[-2], 38)
    trail["sealed_at"] = min(lead["sealed_at"] + DAY * 5, CUT - HOUR)

    # A few more second spellings, on pressings sealed long before any floor, so
    # they move the depot-wide tally without touching a single outlet's pick.
    seen = {}
    for sign in state["countersigns"]:
        for subject in sign["subjects"]:
            key = (subject["path"], subject["digest"])
            seen[key] = seen.get(key, 0) + 1
    quiet = []
    for oid, _ in OUTLETS:
        floor = _outlet(state, oid)["reissue_floor"]
        for pressing in _here(state, oid):
            if pressing["sealed_at"] >= floor - DAY * 60:
                continue
            single = [p for p in pressing["parts"]
                      if _plain(p["path"]) and seen.get((p["path"], p["digest"])) == 1]
            if len(single) >= 2:
                quiet.append((pressing, single))
            if len(quiet) >= 3 * (1 + len(OUTLETS)):
                break
    picks = roll.sample(quiet, 6)
    for pressing, single in picks[:3]:
        single[0]["path"] = _bend_path(single[0]["path"])
    for pressing, single in picks[3:]:
        _respell_subject(state, single[-1], digest=_bend_digest(single[-1]["digest"]))

    return order_marks


# --------------------------------------------------------------------------
# writing the depot out
# --------------------------------------------------------------------------

HANDOVER = """# Depot handover notes

These notes travel with the depot. They are what one release engineer leaves the
next; they are not the reissue policy, which is kept separately and is the only
thing that decides anything.

## What is in here

`outlets.json` lists the shelves this depot publishes to and, for each one, the
reissue floor agreed with that shelf's operator. `pressings.jsonl` is one line
per pressing ever sealed, carrying its outlet, its version, its revision, the
instant it was sealed and its manifest. `countersigns.jsonl` is one line per
builder run that attested content. `embargoes.jsonl` is the embargo log.
`strikes.jsonl` is the strike list.

## Manifests

The manifests came off two generations of packing tooling. The older one wrote a
part path the way the packing recipe happened to spell it; the newer one tidies
the spelling first. Nothing was rewritten when the two archives were merged,
because a manifest is a record of what was sealed and we do not edit records
after the fact. Every path is a path relative to the root of the pressing, and it
denotes the file it denotes however it is spelled.

The same is true of the digests. Some runs wrote a bare hex digest, some wrote
the algorithm in front of it, and the case of the hex was never normalised. It is
one SHA-256 value either way.

## Countersigns

A countersign records what a single builder run attested, and it names its
subjects by content, not by pressing. A run signs the parts it produced, so a
pressing whose parts came off more than one run is attested by more than one
countersign, and a part shared unchanged between pressings is attested once for
all of them. Runs made for staging carry the staging scope and are kept for
audit; they are not release evidence.

Nothing here guarantees a pressing is attested at all. Some were never
countersigned, some were countersigned only in part, and some subjects name a
path whose digest a later rebuild superseded.

## Embargoes and strikes

The embargo log is append-only and unordered: a pressing that has been embargoed,
released and embargoed again carries a row for each, and the rows are not stored
in any particular order. A row with no release instant is still open.

A strike is permanent. Struck pressings are never re-served, and the version a
strike took out is a version this depot has told that shelf not to trust again.
Not every shelf has had to strike anything.
"""


def _settle(roll, rows, marks):
    """Shuffle the embargo log, keeping the marked rows in the order recorded."""
    shuffled = roll.shuffled(rows)
    for group in marks:
        wanted = [row for gid in group for row in shuffled if row["embargo"] == gid]
        slots = sorted(i for i, row in enumerate(shuffled) if row["embargo"] in group)
        for slot, row in zip(slots, wanted):
            shuffled[slot] = row
    return shuffled


def _line(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _write(root: str, state: dict) -> None:
    depot = os.path.join(root, "depot")
    os.makedirs(depot, exist_ok=True)

    outlets = [
        {
            "outlet": row["outlet"],
            "name": row["name"],
            "family": row["family"],
            "reissue_floor": stamp(row["reissue_floor"]),
        }
        for row in state["outlets"]
    ]
    with open(os.path.join(depot, "outlets.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"cut": stamp(CUT), "outlets": outlets},
                            indent=2, sort_keys=True))
        fh.write("\n")

    with open(os.path.join(depot, "pressings.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for row in state["pressings"]:
            fh.write(_line({
                "pressing": row["pressing"],
                "outlet": row["outlet"],
                "version": row["version"],
                "revision": row["revision"],
                "sealed_at": stamp(row["sealed_at"]),
                "line": row["line"],
                "parts": [
                    {"path": p["path"], "digest": p["digest"], "bytes": p["bytes"]}
                    for p in row["parts"]
                ],
            }) + "\n")

    with open(os.path.join(depot, "countersigns.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for row in state["countersigns"]:
            fh.write(_line({
                "countersign": row["countersign"],
                "builder": row["builder"],
                "issued_at": stamp(row["issued_at"]),
                "scope": row["scope"],
                "subjects": row["subjects"],
            }) + "\n")

    with open(os.path.join(depot, "embargoes.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for row in state["embargoes"]:
            fh.write(_line({
                "embargo": row["embargo"],
                "pressing": row["pressing"],
                "opened_at": stamp(row["opened_at"]),
                "released_at": None if row["released_at"] is None else stamp(row["released_at"]),
                "raised_by": row["raised_by"],
            }) + "\n")

    with open(os.path.join(depot, "strikes.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for row in state["strikes"]:
            fh.write(_line({
                "strike": row["strike"],
                "pressing": row["pressing"],
                "struck_at": stamp(row["struck_at"]),
                "reason": row["reason"],
            }) + "\n")

    with open(os.path.join(depot, "HANDOVER.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HANDOVER)


# --------------------------------------------------------------------------
# refusing to ship a depot that does not hold up
# --------------------------------------------------------------------------

def _audit(state: dict, answer: dict, board: dict) -> dict:
    truth = graded(answer)
    named = set(truth["slate"])

    if BARREN in named:
        raise AssertionError("the barren outlet came out with something to reissue")
    if len(named) != len(OUTLETS) - 1:
        raise AssertionError("expected every other outlet to name a pressing")

    where = {p["pressing"]: p["outlet"] for p in state["pressings"]}
    for oid, pid in truth["slate"].items():
        if where[pid] != oid:
            raise AssertionError("outlet %s named a pressing of %s" % (oid, where[pid]))

    for name, other in board.items():
        if other == truth:
            raise AssertionError("reading %s decides nothing on this depot" % name)
        if not named <= set(other["slate"]):
            raise AssertionError("reading %s leaves an outlet with nothing" % name)

    moved = {name for name, other in board.items() if other["slate"] != truth["slate"]}
    if len(moved) < len(READINGS) - 1:
        raise AssertionError("some reading only moves the tally: %s"
                             % sorted(set(board) - moved))

    bent_paths = 0
    for pressing in state["pressings"]:
        for part in pressing["parts"]:
            if part["path"] != tidy_path(part["path"]):
                bent_paths += 1
    bent_subject_paths = 0
    bent_digests = 0
    for sign in state["countersigns"]:
        for subject in sign["subjects"]:
            if subject["path"] != tidy_path(subject["path"]):
                bent_subject_paths += 1
            if subject["digest"] != tidy_digest(subject["digest"]):
                bent_digests += 1
    bent_part_digests = sum(
        1 for pressing in state["pressings"] for part in pressing["parts"]
        if part["digest"] != tidy_digest(part["digest"])
    )
    counts = {
        "outlets": len(state["outlets"]),
        "pressings": len(state["pressings"]),
        "parts": sum(len(p["parts"]) for p in state["pressings"]),
        "countersigns": len(state["countersigns"]),
        "subjects": sum(len(c["subjects"]) for c in state["countersigns"]),
        "embargoes": len(state["embargoes"]),
        "strikes": len(state["strikes"]),
        "bent_paths": bent_paths + bent_subject_paths,
        "bent_digests": bent_digests + bent_part_digests,
    }
    for key, low, high in (("bent_paths", 3, 9), ("bent_digests", 3, 9)):
        if not low <= counts[key] <= high:
            raise AssertionError("%s is %d, outside %d..%d" % (key, counts[key], low, high))
    if counts["pressings"] < 700 or counts["parts"] < 6000:
        raise AssertionError("the depot came out too small to hide anything in")

    _claims(state, counts)
    return counts


def _claims(state: dict, counts: dict) -> None:
    """Every checkable sentence the shipped documents make, asserted of the data."""
    spellings = set()
    prefixed = upper = 0
    for pressing in state["pressings"]:
        for part in pressing["parts"]:
            if part["path"] != tidy_path(part["path"]):
                spellings.add(_shape(part["path"]))
            if part["digest"] != tidy_digest(part["digest"]):
                prefixed += ":" in part["digest"]
                upper += ":" not in part["digest"]
    for sign in state["countersigns"]:
        for subject in sign["subjects"]:
            if subject["path"] != tidy_path(subject["path"]):
                spellings.add(_shape(subject["path"]))
            if subject["digest"] != tidy_digest(subject["digest"]):
                prefixed += ":" in subject["digest"]
                upper += ":" not in subject["digest"]
    if len(spellings) < 2:
        raise AssertionError("the depot shows only one second spelling of a path")
    if not prefixed or not upper:
        raise AssertionError("the depot does not show both second spellings of a digest")

    struck_on = {row["pressing"] for row in state["strikes"]}
    home = {p["pressing"]: p["outlet"] for p in state["pressings"]}
    with_strikes = {home[pid] for pid in struck_on}
    bare = [oid for oid, _ in OUTLETS if oid not in with_strikes]
    if bare != [UNBARRED]:
        raise AssertionError("expected exactly one outlet with no strike, found %s" % bare)

    attested = set()
    staging_only = set()
    for sign in state["countersigns"]:
        for subject in sign["subjects"]:
            key = (tidy_path(subject["path"]), tidy_digest(subject["digest"]))
            if sign["scope"] == "release":
                attested.add(key)
            else:
                staging_only.add(key)
    bare_pressings = partial = staged = superseded = 0
    for pressing in state["pressings"]:
        keys = [(tidy_path(p["path"]), tidy_digest(p["digest"])) for p in pressing["parts"]]
        hits = sum(1 for key in keys if key in attested)
        if hits == 0:
            bare_pressings += 1
        elif hits < len(keys):
            partial += 1
            if any(key in staging_only for key in keys):
                staged += 1
    seen_paths = {path for path, _ in attested}
    for pressing in state["pressings"]:
        for part in pressing["parts"]:
            key = (tidy_path(part["path"]), tidy_digest(part["digest"]))
            if key not in attested and key[0] in seen_paths:
                superseded += 1
    for name, value in (("never countersigned", bare_pressings),
                        ("countersigned in part", partial),
                        ("attested only from staging", staged),
                        ("superseded subject digests", superseded)):
        if value < 2:
            raise AssertionError("the depot shows %d pressings %s" % (value, name))

    shared = 0
    owners = {}
    for pressing in state["pressings"]:
        for part in pressing["parts"]:
            owners.setdefault((part["path"], part["digest"]), set()).add(pressing["pressing"])
    shared = sum(1 for who in owners.values() if len(who) > 1)
    if shared < 20:
        raise AssertionError("no part is shared unchanged between pressings")

    rows = {}
    for row in state["embargoes"]:
        rows.setdefault(row["pressing"], []).append(row)
    if sum(1 for group in rows.values() if len(group) > 1) < 10:
        raise AssertionError("no pressing carries more than one embargo row")
    if not any(row["released_at"] is None for row in state["embargoes"]):
        raise AssertionError("no embargo row is still open")

    for pressing in state["pressings"]:
        pieces = pressing["version"].split(".")
        if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
            raise AssertionError("version %s is not dotted numbers" % pressing["version"])

    counts["bare_pressings"] = bare_pressings
    counts["shared_parts"] = shared


def _shape(spelling: str) -> str:
    if spelling.startswith("./"):
        return "leading"
    return "doubled" if "//" in spelling else "inner"


def build(root: str) -> dict:
    """Write the depot under `root` and return the answer it implies."""
    _BENT["path"] = 0
    _BENT["digest"] = 0
    roll = Roll(SEED)
    state = _lay_out(roll)
    pools = state["pools"]
    marks = _plant(state, roll, pools)

    state["pressings"] = roll.shuffled(state["pressings"])
    state["countersigns"] = roll.shuffled(state["countersigns"])
    state["strikes"] = roll.shuffled(state["strikes"])
    state["embargoes"] = _settle(roll, state["embargoes"], marks)

    answer = resolve(state)
    board = {name: graded(resolve(state, (name,))) for name in READINGS}
    counts = _audit(state, answer, board)
    _write(root, state)
    return {"answer": graded(answer), "board": board, "counts": counts}
