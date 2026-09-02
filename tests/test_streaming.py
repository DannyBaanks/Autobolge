from malbolge_translator.streaming import translate_continuous


def test_continuous_segments_form_one_verified_program():
    result = translate_continuous("Hi", segment_chars=1)
    assert result.output == "Hi"
    assert len(result.segments) == 2
    assert all(segment.opcodes for segment in result.segments)


def test_continuous_generation_obeys_classic_program_limit():
    try:
        translate_continuous("Hi", segment_chars=1, max_program_length=101)
    except Exception as exc:
        assert "exceed" in str(exc)
    else:
        raise AssertionError("expected Classic program-length rejection")
