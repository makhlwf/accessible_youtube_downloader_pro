from media_player.timecodes import extract_timecodes, format_timecode, parse_timecode


def test_parse_timecode_accepts_minutes_and_hours():
    assert parse_timecode("2:47") == 167
    assert parse_timecode("12:03") == 723
    assert parse_timecode("1:02:03") == 3723


def test_parse_timecode_rejects_invalid_seconds():
    assert parse_timecode("2:99") is None
    assert parse_timecode("1:60:00") is None
    assert parse_timecode("not a time") is None


def test_extract_timecodes_from_comment_text():
    timestamps = extract_timecodes("The 2:47 thing was cool, and 1:02:03 too.")

    assert timestamps == [
        {"label": "2:47", "seconds": 167},
        {"label": "1:02:03", "seconds": 3723},
    ]


def test_format_timecode_uses_colon_notation():
    assert format_timecode(167) == "2:47"
    assert format_timecode(3723) == "1:02:03"
