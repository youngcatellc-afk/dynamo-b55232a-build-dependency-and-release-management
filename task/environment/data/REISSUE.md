# Reissue policy

This document is normative. It fixes, on its own, which pressing each outlet reissues.
Nothing else in the depot changes any of it.

## The event

The key this depot signs under was withdrawn at the **cut instant**, which
`/app/depot/outlets.json` records as `cut`. Every outlet the depot publishes to is owed
one archived pressing to re-sign and re-publish. That pressing is the outlet's **reissue
candidate**.

## What the depot holds

A **pressing** is one sealed build, published to exactly one outlet. It carries a version,
a revision, the instant it was sealed, and a manifest.

A **part** is one file of a pressing's manifest: the path the file sits at inside the
pressing, and the SHA-256 digest of its bytes. The path is the file it denotes and the
digest is the value it names; neither is the string it happens to be written with.

A **countersign** is the record of one builder run. It names its subjects by content — a
path and a digest — and not by pressing. A run attests the parts it produced, so the parts
of one pressing may be spread over several countersigns, and a part shared unchanged
between pressings is attested for all of them at once. A countersign carries a scope;
only the `release` scope is release evidence.

An **embargo** is one row of the embargo log. The log is append-only and unordered, and a
pressing that has been embargoed more than once carries a row for each. A row with no
release instant has not been released.

A **strike** withdraws a pressing permanently.

A **version** is dotted numbers. Versions order as numbers, component by component.

## The candidate

A pressing is eligible for its outlet when all five of these hold.

1. **Sealed in the window.** Its sealing instant is at or after that outlet's
   `reissue_floor` and at or before the cut. Both bounds are inclusive.

2. **Not struck.** No strike names it.

3. **Over the strike bar.** An outlet's strike bar is the greatest version among the
   pressings of that outlet that a strike names. An eligible pressing's version must be
   strictly greater than that bar. An outlet no strike names has no bar, and nothing on it
   is barred.

4. **Not under embargo at the cut.** A pressing is under embargo at the cut if any embargo
   row naming it was open then — opened at or before the cut, and either never released or
   released strictly after it.

5. **Countersigned.** Every part of its manifest is named as a subject of some `release`
   countersign, at the same path and with the same digest. Subjects drawn from any number
   of countersigns count together.

Among the pressings eligible for an outlet, the **reissue candidate** is the one with the
greatest revision. If more than one shares that revision, it is the one of those sealed
latest. If more than one still shares that, it is the one whose pressing identifier sorts
first.

An outlet with no eligible pressing has no reissue candidate.

## Counting

A pressing is **countersigned** when clause 5 holds of it. That is a fact about the
pressing alone: it does not depend on the outlet, on the window, on strikes or on
embargoes, and it is asked of every pressing the depot holds.
