import pytest

from app.draw import DrawError, draw


def test_everyone_gives_and_receives_once():
    ids = [str(i) for i in range(10)]
    for _ in range(200):
        pairs = draw(ids)
        assert sorted(pairs) == sorted(ids)
        assert sorted(pairs.values()) == sorted(ids)
        assert all(g != r for g, r in pairs.items())


def test_groups_are_respected():
    ids = ["ana", "rui", "marta", "joao", "ines", "pedro"]
    groups = {"ana": "a", "rui": "a", "marta": "b", "joao": "b", "ines": None, "pedro": None}
    for _ in range(200):
        pairs = draw(ids, groups)
        for g, r in pairs.items():
            assert not (groups[g] and groups[g] == groups[r])


def test_tight_but_possible():
    # Half the people in one group: they must all draw (and be drawn by) the other half.
    ids = list("abcdef")
    groups = {"a": "x", "b": "x", "c": "x"}
    for _ in range(100):
        pairs = draw(ids, groups)
        for g in "abc":
            assert pairs[g] in "def"


def test_impossible_group():
    with pytest.raises(DrawError):
        draw(list("abcde"), {"a": "x", "b": "x", "c": "x"})


def test_too_few():
    with pytest.raises(DrawError):
        draw(["a", "b"])
