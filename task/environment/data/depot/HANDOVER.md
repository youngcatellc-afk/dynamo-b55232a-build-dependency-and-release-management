# Depot handover notes

These notes travel with the depot. They are what one release engineer leaves the
next; they are not the reissue policy, which is kept separately and is the only
thing that decides anything.

## What is in here

`outlets.json` lists the shelves this depot publishes to and, for each one, the
reissue floor agreed with the operator of that shelf. `pressings.jsonl` is one line
per pressing ever sealed, carrying its outlet, its version, its revision, the
instant it was sealed and its manifest. `countersigns.jsonl` is one line per
builder run that attested content. `embargoes.jsonl` is the embargo log.
`strikes.jsonl` is the strike list.

## House rules

Nothing in the depot is edited after the fact. A pressing record is what was
sealed, a countersign is what a builder run said at the time, and a log row stays
as it was written. Where something later turned out to be wrong we add a row; we
do not go back and tidy.

Retention is indefinite. Pressings sealed long before any floor now in force are
all still here, and so are the runs that attested them, and so is every row ever
written to the two logs.

Nothing here guarantees a pressing is attested. Plenty are not.

## Who to ask

Shelf agreements, and any change to a reissue floor, go through the release desk.
The signing arrangements are with the security desk. Neither of them keeps
anything in this depot.
