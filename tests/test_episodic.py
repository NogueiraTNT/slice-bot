from sally_cibote.memory.episodic import EpisodicMemory


def test_learns_name_from_portuguese(tmp_path):
    mem = EpisodicMemory(tmp_path / "e.json")
    assert mem.maybe_learn_name("Oi, meu nome é Daniel") == "Daniel"
    assert mem.user_name == "Daniel"
    other = EpisodicMemory(tmp_path / "e.json")
    assert other.user_name == "Daniel"


def test_silence_grows_without_interaction(tmp_path):
    mem = EpisodicMemory(tmp_path / "e.json")
    assert mem.silence_s() > 1000
    mem.note_interaction("Slice oi")
    assert mem.silence_s() < 2
