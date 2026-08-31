# Depot handover notes

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
