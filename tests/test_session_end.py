from sally_cibote.voice.session_end import is_session_end


def test_bye_phrases():
    assert is_session_end("tchau")
    assert is_session_end("Slice, tchau")
    assert is_session_end("até logo")
    assert is_session_end("pode parar")
    assert not is_session_end("vai chover")
    assert not is_session_end("")
