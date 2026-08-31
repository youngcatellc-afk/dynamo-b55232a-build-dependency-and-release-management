The key this firmware depot signs under was withdrawn, and every outlet it publishes to has
to be given one archived pressing to re-sign and re-publish. Work out which pressing each
outlet gets.

`/app/depot` is the depot: `outlets.json` for the outlets and the instant the key was
withdrawn, `pressings.jsonl` for every pressing ever sealed and its manifest,
`countersigns.jsonl` for what the builder runs attested, `embargoes.jsonl` for the embargo
log, `strikes.jsonl` for the strike list, and `HANDOVER.md` for the notes the depot carries
with it.

`/app/REISSUE.md` is the reissue policy. It is normative and it settles, on its own, which
pressing each outlet is owed.

Write your answer to `/app/reissue_slate.json`, a JSON object carrying exactly these two
keys and no others.

`slate` — an object. One member for each outlet that has a reissue candidate: the key is
the outlet identifier and the value is that candidate's pressing identifier, both as the
strings the depot writes them with. An outlet with no reissue candidate must not appear.

`countersigned` — an integer: how many pressings in the whole depot are countersigned.

Leave every file under `/app/depot` exactly as you found it.
