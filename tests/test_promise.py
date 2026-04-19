"""Tests for strict promise-tag parsing."""

import pytest

from ralphify._promise import has_promise_completion, parse_promise_tags


class TestParsePromiseTags:
    @pytest.mark.parametrize(
        "raw_text", [None, "", "plain text", "<promise>missing close"]
    )
    def test_parse_promise_tags_invalid_input_returns_empty_list(self, raw_text):
        assert parse_promise_tags(raw_text) == []

    def test_parse_promise_tags_normalizes_whitespace_and_preserves_unicode(self):
        text = (
            "before "
            "<promise>\n  CUSTOM\tDONE  \n</promise> "
            "middle "
            "<promise>✅ shipped</promise>"
        )

        assert parse_promise_tags(text) == ["CUSTOM DONE", "✅ shipped"]


class TestHasPromiseCompletion:
    def test_has_promise_completion_matches_only_exact_tag_payload(self):
        text = (
            "raw CUSTOM_DONE text "
            "<promise>CUSTOM_DONE_NOW</promise> "
            "<promise>CUSTOM_DONE</promise>"
        )

        assert has_promise_completion(text, "CUSTOM_DONE") is True
        assert has_promise_completion(text, "CUSTOM_DONE_NOW") is True
        assert has_promise_completion(text, "CUSTOM") is False

    def test_has_promise_completion_ignores_wrong_case_and_malformed_tags(self):
        text = "<PROMISE>CUSTOM_DONE</PROMISE><promise>CUSTOM_DONE</promise-ish>"

        assert has_promise_completion(text, "CUSTOM_DONE") is False

    def test_has_promise_completion_normalizes_completion_signal_whitespace(self):
        text = "<promise>\n  CUSTOM\tDONE  \n</promise>"

        assert has_promise_completion(text, "CUSTOM DONE") is True
        assert has_promise_completion(text, "CUSTOM\tDONE") is True
