import time

from sally_cibote.memory.proactive import ProactiveController


def test_proactive_fires_after_long_silence(tmp_path):
    ctl = ProactiveController(
        root=tmp_path,
        stage="newborn",
        silence_threshold_s=10.0,
        cooldown_s=1.0,
        speak_hz_threshold=5.0,
    )
    # Force "long silence" by never interacting; boost silence sensor via low threshold
    ctl.episodic.last_interaction_ts = time.time() - 120
    ctl.episodic.save()
    # Strong morning + silence should drive SPEAK_GREET
    prop = None
    for _ in range(5):
        prop = ctl.tick(steps=80)
        if prop:
            break
    assert prop is not None
    assert "Bom" in prop.text or "Boa" in prop.text or "aprendendo" in prop.text


def test_busy_blocks_proactive(tmp_path):
    ctl = ProactiveController(
        root=tmp_path,
        silence_threshold_s=5.0,
        cooldown_s=0.0,
        speak_hz_threshold=1.0,
    )
    ctl.episodic.last_interaction_ts = time.time() - 120
    ctl.set_busy(True)
    assert ctl.tick(steps=80) is None


def test_learns_name_and_uses_it(tmp_path):
    ctl = ProactiveController(
        root=tmp_path,
        silence_threshold_s=5.0,
        cooldown_s=0.0,
        speak_hz_threshold=5.0,
    )
    ctl.note_user_text("meu nome é Daniel")
    assert ctl.episodic.user_name == "Daniel"
    ctl.episodic.last_interaction_ts = time.time() - 120
    prop = None
    for _ in range(8):
        prop = ctl.tick(steps=80)
        if prop and "Daniel" in prop.text:
            break
    assert prop is not None
    assert "Daniel" in prop.text
