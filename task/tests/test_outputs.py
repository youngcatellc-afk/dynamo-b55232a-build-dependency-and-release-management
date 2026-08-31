"""Grade /app/reissue_slate.json against a depot the grader rebuilds for itself."""

from __future__ import annotations

import pytest

import bench


@pytest.fixture(scope="module")
def truth():
    """The rebuilt depot, its answer, and the board of misreadings it defeats."""
    return bench.ground()


@pytest.fixture(scope="module")
def slate():
    """The file the instruction asks for, at the path the instruction names."""
    outcome = bench.submitted()
    if "complaint" in outcome:
        pytest.fail(outcome["complaint"])
    return outcome["body"]


def test_the_rebuilt_depot_holds_up_before_anything_is_graded(truth):
    """Two independent readings agree, and no clause of the policy is dead on it.

    The board the builder keeps covers every misreading the depot is built to
    punish — ordering instants by their written text, folding a manifest to one
    row per path, comparing a path or a digest as the string it was written with,
    reducing the embargo log to a row per pressing, and each window bound, strike
    clause and tie-break read the other way. Every one of them has to change a
    graded value, or a clause of the policy is dead on the data that ships.
    """
    assert truth["counts"]["pressings"] > 2000, "the rebuilt depot came out too small"
    assert len(truth["board"]) >= 22, "a reading of the policy went missing from the board"
    assert len(truth["answer"]["slate"]) == len(truth["outlets"]) - 1, (
        "expected every outlet but one to be owed a pressing"
    )


def test_the_depot_was_left_as_it_was_found(truth):
    """The instruction requires /app/depot untouched, file set and contents alike."""
    found = bench.shipped_seal()
    assert found is not None, "/app/depot is missing"
    assert sorted(found) == sorted(truth["seal"]), (
        "the set of files under /app/depot changed: %s"
        % sorted(set(found) ^ set(truth["seal"]))
    )
    changed = [name for name in sorted(found) if found[name] != truth["seal"][name]]
    assert not changed, "these depot files were modified: %s" % changed


def test_the_slate_is_a_json_object_with_exactly_the_two_keys(slate):
    """The answer is a JSON object carrying `slate` and `countersigned`, and nothing else."""
    assert isinstance(slate, dict), "the answer must be a JSON object"
    assert tuple(sorted(slate)) == bench.KEYS, (
        "expected exactly %s, found %s" % (list(bench.KEYS), sorted(slate))
    )
    assert isinstance(slate["slate"], dict), "`slate` must be a JSON object"
    assert bench.whole_number(slate["countersigned"]), (
        "`countersigned` must be a JSON integer"
    )


def test_the_slate_maps_outlets_of_this_depot_to_their_own_pressings(slate, truth):
    """Keys are outlet identifiers; each value is a pressing published to that outlet."""
    given = slate["slate"]
    unknown = sorted(set(given) - set(truth["outlets"]))
    assert not unknown, "these are not outlets of this depot: %s" % unknown
    for outlet, pressing in sorted(given.items()):
        assert bench.plain_text(pressing), (
            "%s names %r, which is not a pressing identifier" % (outlet, pressing)
        )
        assert pressing in truth["home"], "%s names no pressing this depot holds" % outlet
        assert truth["home"][pressing] == outlet, (
            "%s names %s, which was published to %s"
            % (outlet, pressing, truth["home"][pressing])
        )


def test_every_outlet_that_is_owed_a_pressing_appears(slate, truth):
    """An outlet with a reissue candidate must be named in the slate."""
    missing = sorted(set(truth["answer"]["slate"]) - set(slate["slate"]))
    assert not missing, "these outlets are owed a pressing and were left out: %s" % missing


def test_an_outlet_owed_nothing_is_left_out(slate, truth):
    """An outlet with no eligible pressing must be absent, not null and not empty."""
    spurious = sorted(set(slate["slate"]) - set(truth["answer"]["slate"]))
    assert not spurious, "these outlets have no reissue candidate: %s" % spurious


def test_each_outlet_names_the_pressing_the_policy_picks(slate, truth):
    """Every named pressing is the eligible one the tie-breaks settle on."""
    wanted = truth["answer"]["slate"]
    given = slate["slate"]
    wrong = {
        outlet: (given.get(outlet), pressing)
        for outlet, pressing in sorted(wanted.items())
        if given.get(outlet) != pressing
    }
    assert not wrong, "outlet: (named, owed) -> %s" % wrong


def test_the_count_of_countersigned_pressings_is_right(slate, truth):
    """The count covers every pressing in the depot, whatever outlet it went to."""
    assert slate["countersigned"] == truth["answer"]["countersigned"], (
        "counted %s countersigned pressings, the depot holds %s"
        % (slate["countersigned"], truth["answer"]["countersigned"])
    )
