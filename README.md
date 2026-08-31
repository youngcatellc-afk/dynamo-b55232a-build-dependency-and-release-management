# dynamo/reissue-slate

A firmware distribution service has had its signing key withdrawn. `task/` asks an agent to
work out, for each of the fourteen outlets its depot publishes to, which single archived
pressing is eligible to be re-signed and re-published, and to write that mapping to
`/app/reissue_slate.json` together with a count of the pressings the builders have fully
attested.

This note is context for a reviewer. The task itself is `task/instruction.md` and the
policy the agent works to is `task/environment/data/REISSUE.md`.

## Where the difficulty is

Eligibility is a conjunction of five clauses — sealed inside the outlet's window, not
struck, over the version bar the strike list sets for that outlet, not under an embargo
open at the cut, and countersigned in full — and the pick among the eligible is settled by
three tie-breaks in turn. Nothing there is hard on its own. What is hard is that every one
of those eight has a coherent wrong reading which still yields a complete, well-formed
slate naming a plausible pressing of the right outlet, and the depot offers no way to tell
the two apart: no oracle, no invariant that breaks, no entry that comes out missing.

Four of those readings are the ones a careful engineer still reaches for, and each was
measured against the depot that ships rather than assumed:

- a countersign names its subjects by content and not by pressing, so coverage is a
  question about the union of every release run — binding one run to one pressing drops a
  build whose parts came off two of them;
- the embargo log is append-only and unordered, so a pressing can carry several rows and is
  shut if any of them was open at the cut — keeping one row per pressing frees a build that
  is still embargoed, and it fails whether you keep the first row or the last;
- the manifests came off two generations of packing tooling, so ten values in the depot are
  written a second way — the same file, the same digest, a different string — and comparing
  the strings as written uncovers the build that should have won;
- the strike list does double duty: it removes pressings, and the greatest version it names
  on an outlet is a bar that outlet will not reissue back to.

Attractor pressings are planted on separate outlets for each of these: a higher-revision
build that a superseded subject digest makes look attested, one that a released embargo row
makes look free, one attested only from a staging run, one that was struck, and two that sit
on and just under the version bar. Each is the build a solver lands on if it prunes early.

## How it is graded

Ground truth is never read from `/app`. `task/tests/bench.py` rebuilds the whole depot from
`task/tests/fixture/forge.py` into a private temporary directory — one pinned 64-bit
generator, no clock, no locale, no network, no unseeded entropy — and derives the answer
there. It derives it twice: once from the structures the builder built and once by
`task/tests/fixture/sift.py`, a separate reader that re-parses the written files, settles
paths by walking their components, compares instants as text, and walks each outlet in rank
order. The grader fails closed unless the two agree. `task/solution/solve.py` is a third
implementation and is what the oracle run exercises.

Grading is exact match with no tolerance: eight test functions, one per stated requirement,
and the reward is read out of the CTRF report so a truncated or skipped suite cannot score.
`/app/depot` is also checked file-for-file and hash-for-hash against the rebuilt copy, which
both enforces the instruction's read-only requirement and acts as a drift canary between the
committed fixture and the generator.

The builder refuses to emit a depot at all unless nineteen distinct misreadings of the
policy each change a graded value without leaving any outlet empty, so no clause of the
policy can be dead on the data that ships.
