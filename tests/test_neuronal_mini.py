from sally_cibote.memory.neuronal import MiniLifBrain


def _peak(brain: MiniLifBrain, morning: float, steps: int = 60) -> float:
    brain.stimulate({"TIME_MORNING": morning})
    peak = 0.0
    for _ in range(steps):
        brain.step(1.0)
        peak = max(peak, brain.motors()["LOG_TICK"])
    return peak


def test_morning_drives_motor_more_than_night():
    brain = MiniLifBrain(seed=1)
    night = _peak(brain, 0.0)
    morning = _peak(brain, 1.0)
    assert morning > night


def test_silence_drives_speak_greet():
    brain = MiniLifBrain(seed=4)
    brain.stimulate({"TIME_MORNING": 0.3, "SILENCE": 0.0})
    quiet = 0.0
    for _ in range(50):
        brain.step(1.0)
        quiet = max(quiet, brain.motors()["SPEAK_GREET"])
    brain.stimulate({"TIME_MORNING": 0.3, "SILENCE": 1.0})
    loud = 0.0
    for _ in range(50):
        brain.step(1.0)
        loud = max(loud, brain.motors()["SPEAK_GREET"])
    assert loud > quiet


def test_positive_reward_increases_learned_weights():
    brain = MiniLifBrain(seed=2)
    _peak(brain, 1.0, steps=40)
    before = (brain.learned_sf, brain.learned_fm)
    brain.on_reward(+1)
    assert brain.learned_sf >= before[0]
    assert brain.learned_fm >= before[1]


def test_save_load_roundtrip(tmp_path):
    brain = MiniLifBrain(seed=3)
    _peak(brain, 1.0, steps=30)
    brain.on_reward(+1)
    path = tmp_path / "w.json"
    brain.save(path)
    other = MiniLifBrain(seed=3)
    other.load(path)
    assert abs(other.learned_sf - brain.learned_sf) < 1e-9
    assert abs(other.learned_fm - brain.learned_fm) < 1e-9


def test_neuron_count_in_mini_range():
    n = MiniLifBrain().snapshot()["neuron_count"]
    assert 20 <= n <= 50
