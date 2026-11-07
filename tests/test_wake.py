from sally_cibote.voice.wake import (
    contains_wake_word,
    normalize_pt,
    score_wake,
    strip_wake_prefix,
)


def test_wake_slice_alone():
    assert contains_wake_word("Slice")
    assert contains_wake_word("slice")
    assert contains_wake_word("Slyce")
    assert contains_wake_word("Slise")
    assert contains_wake_word("Slicey")
    assert contains_wake_word("É lice.")
    assert contains_wake_word("e lice")
    assert contains_wake_word("e-lice")
    assert contains_wake_word("aslice")
    assert contains_wake_word("elice")
    assert contains_wake_word("É o seu lice.")


def test_wake_slice_with_greeting():
    assert contains_wake_word("Olá Slice")
    assert contains_wake_word("oi slice toca musica")


def test_wake_rejects_unrelated():
    assert not contains_wake_word("bom dia")
    assert not contains_wake_word("")
    assert not contains_wake_word("sales")


def test_wake_confidence_scores():
    m = score_wake("Slice")
    assert m.hit and m.score >= 0.9
    m2 = score_wake("e-lice")
    assert m2.hit and m2.score >= 0.55
    m3 = score_wake("tudo bem")
    assert not m3.hit and m3.score < 0.55


def test_strip_wake_keeps_command():
    assert "tocar musica" in strip_wake_prefix("olá Slice tocar musica")
    assert strip_wake_prefix("Slice") == ""
    assert normalize_pt("Olá") == "ola"
