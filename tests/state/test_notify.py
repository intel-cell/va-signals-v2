"""Tests for state notification formatting."""

from src.state.notify import format_state_alert, format_state_digest


class TestFormatStateAlert:
    """Tests for format_state_alert function."""

    def test_empty_input_returns_none(self):
        """Empty list returns None."""
        assert format_state_alert([]) is None
        assert format_state_alert(None) is None

    def test_single_signal_basic(self):
        """Single signal formats correctly."""
        signals = [
            {
                "state": "TX",
                "title": "Texas Veterans Commission suspends PACT Act outreach",
                "url": "https://example.com/article",
                "program": "PACT Act",
                "source_id": "tx_tvc_news",
                "keywords_matched": "suspend",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        assert "text" in result
        text = result["text"]

        # Check header
        assert "*State Intelligence Alert*" in text
        # Check state tag
        assert "*[TX]*" in text
        # Check Slack link format
        assert (
            "<https://example.com/article|Texas Veterans Commission suspends PACT Act outreach>"
            in text
        )
        # Check program
        assert "_PACT Act_" in text
        # Check source
        assert "tx_tvc_news" in text
        # Check triggers
        assert "Triggers: suspend" in text

    def test_multiple_signals(self):
        """Multiple signals format correctly with blank lines between."""
        signals = [
            {
                "state": "TX",
                "title": "Texas Veterans Commission suspends PACT Act outreach",
                "url": "https://example.com/tx-article",
                "program": "PACT Act",
                "source_id": "tx_tvc_news",
                "keywords_matched": "suspend",
            },
            {
                "state": "CA",
                "title": "CalVet reports 30% backlog in toxic exposure claims",
                "url": "https://example.com/ca-article",
                "program": "PACT Act",
                "source_id": "ca_calvet_news",
                "keywords_matched": "backlog",
            },
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]

        # Check both states appear
        assert "*[TX]*" in text
        assert "*[CA]*" in text
        # Check both triggers
        assert "Triggers: suspend" in text
        assert "Triggers: backlog" in text

    def test_keywords_as_list(self):
        """Keywords provided as list format correctly."""
        signals = [
            {
                "state": "FL",
                "title": "Florida suspends benefits processing",
                "url": "https://example.com/fl",
                "program": "General",
                "source_id": "fl_dva_news",
                "keywords_matched": ["suspend", "delay", "halt"],
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Triggers: suspend, delay, halt" in text

    def test_keywords_as_comma_string(self):
        """Keywords provided as comma-separated string format correctly."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal",
                "url": "https://example.com",
                "program": "General",
                "source_id": "test_source",
                "keywords_matched": "suspend, delay, halt",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Triggers: suspend, delay, halt" in text

    def test_missing_keywords(self):
        """Signal without keywords does not show Triggers line."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal",
                "url": "https://example.com",
                "program": "General",
                "source_id": "test_source",
                "keywords_matched": None,
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Triggers:" not in text

    def test_empty_keywords(self):
        """Signal with empty keywords does not show Triggers line."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal",
                "url": "https://example.com",
                "program": "General",
                "source_id": "test_source",
                "keywords_matched": "",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Triggers:" not in text

    def test_missing_program_defaults_to_general(self):
        """Missing program field defaults to 'General'."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal",
                "url": "https://example.com",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "_General_" in text

    def test_missing_state_defaults_to_question_marks(self):
        """Missing state field defaults to '??'."""
        signals = [
            {
                "title": "Test signal",
                "url": "https://example.com",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "*[??]*" in text

    def test_missing_url_no_link(self):
        """Signal without URL shows title without link formatting."""
        signals = [
            {
                "state": "TX",
                "title": "Test signal without URL",
                "url": "",
                "program": "General",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        # Should not have Slack link format
        assert "<|" not in text
        assert "Test signal without URL" in text

    def test_missing_title_defaults_to_unknown(self):
        """Missing title field defaults to 'Unknown'."""
        signals = [
            {
                "state": "TX",
                "url": "https://example.com",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "Unknown" in text

    def test_missing_source_id_defaults_to_unknown(self):
        """Missing source_id field defaults to 'unknown'."""
        signals = [
            {
                "state": "TX",
                "title": "Test",
                "url": "https://example.com",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        assert "| unknown" in text

    def test_slack_link_format_with_special_characters(self):
        """URL with special characters formats correctly in Slack link."""
        signals = [
            {
                "state": "TX",
                "title": "Test & Title with <special> chars",
                "url": "https://example.com/path?param=value&other=123",
                "program": "General",
                "source_id": "test_source",
            }
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]
        # Slack link should contain URL and title
        assert "<https://example.com/path?param=value&other=123|" in text

    def test_format_matches_design_spec(self):
        """Output matches the design spec example format."""
        signals = [
            {
                "state": "Texas",
                "title": "Texas Veterans Commission suspends PACT Act outreach",
                "url": "https://example.com/source",
                "program": "PACT Act",
                "source_id": "Source",
                "keywords_matched": "suspend",
            },
            {
                "state": "California",
                "title": "CalVet reports 30% backlog in toxic exposure claims",
                "url": "https://example.com/source2",
                "program": "PACT Act",
                "source_id": "Source",
                "keywords_matched": "backlog",
            },
        ]

        result = format_state_alert(signals)

        assert result is not None
        text = result["text"]

        # Verify structure matches design spec
        lines = text.split("\n")

        # First line is header
        assert lines[0] == "*State Intelligence Alert*"

        # Second line is blank
        assert lines[1] == ""

        # Check bullet point format
        assert any(line.startswith("• *[Texas]*") for line in lines)
        assert any(line.startswith("• *[California]*") for line in lines)


class TestFormatStateDigest:
    """Tests for format_state_digest function."""

    def test_empty_dict_returns_none(self):
        """Empty dict returns None."""
        result = format_state_digest({})
        assert result is None

    def test_dict_with_empty_lists_returns_none(self):
        """Dict with only empty lists returns None."""
        result = format_state_digest({"TX": [], "CA": []})
        assert result is None

    def test_single_state_single_signal(self):
        """Single state with single signal formats correctly."""
        signals_by_state = {
            "Texas": [
                {
                    "title": "Texas Veterans Commission update",
                    "url": "https://example.com/tx",
                    "program": "PACT Act",
                    "severity": "medium",
                    "pub_date": "2024-01-15",
                }
            ]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        assert "text" in result
        text = result["text"]

        # Check header
        assert "*State Intelligence Weekly Digest*" in text
        # Check state
        assert "*Texas*" in text
        # Check program with singular count
        assert "_PACT Act_ (1 signal)" in text
        # Check Slack link format
        assert "<https://example.com/tx|Texas Veterans Commission update>" in text

    def test_multiple_states_sorted_alphabetically(self):
        """States are sorted alphabetically."""
        signals_by_state = {
            "Texas": [{"title": "TX Signal", "url": "https://tx.com", "program": "General"}],
            "California": [{"title": "CA Signal", "url": "https://ca.com", "program": "General"}],
            "Florida": [{"title": "FL Signal", "url": "https://fl.com", "program": "General"}],
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # Find positions of state headers
        ca_pos = text.find("*California*")
        fl_pos = text.find("*Florida*")
        tx_pos = text.find("*Texas*")

        # Verify alphabetical order
        assert ca_pos < fl_pos < tx_pos

    def test_programs_grouped_and_sorted(self):
        """Signals are grouped by program and programs are sorted."""
        signals_by_state = {
            "Texas": [
                {"title": "Signal 1", "url": "https://1.com", "program": "PACT Act"},
                {"title": "Signal 2", "url": "https://2.com", "program": "Community Care"},
                {"title": "Signal 3", "url": "https://3.com", "program": "PACT Act"},
            ]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # Community Care should come before PACT Act (alphabetically)
        cc_pos = text.find("_Community Care_")
        pact_pos = text.find("_PACT Act_")
        assert cc_pos < pact_pos

        # PACT Act should show 2 signals
        assert "_PACT Act_ (2 signals)" in text
        # Community Care should show 1 signal
        assert "_Community Care_ (1 signal)" in text

    def test_singular_plural_signal_count(self):
        """Signal count uses correct singular/plural form."""
        signals_by_state = {
            "Texas": [
                {"title": "Signal 1", "url": "https://1.com", "program": "Program A"},
                {"title": "Signal 2", "url": "https://2.com", "program": "Program B"},
                {"title": "Signal 3", "url": "https://3.com", "program": "Program B"},
            ]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # 1 signal - singular
        assert "_Program A_ (1 signal)" in text
        # 2 signals - plural
        assert "_Program B_ (2 signals)" in text

    def test_five_signal_limit_per_program(self):
        """Only first 5 signals shown per program, with '+X more' indicator."""
        signals_by_state = {
            "Texas": [
                {"title": f"Signal {i}", "url": f"https://{i}.com", "program": "PACT Act"}
                for i in range(1, 9)  # 8 signals
            ]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # Should show count of 8
        assert "_PACT Act_ (8 signals)" in text

        # Should show first 5 signals
        assert "Signal 1" in text
        assert "Signal 2" in text
        assert "Signal 3" in text
        assert "Signal 4" in text
        assert "Signal 5" in text

        # Should show '+3 more' indicator
        assert "(+3 more)" in text

        # Should NOT show signals 6, 7, 8 as titles
        lines = text.split("\n")
        title_lines = [
            line for line in lines if "Signal 6" in line or "Signal 7" in line or "Signal 8" in line
        ]
        # These should only appear in the count, not as individual items
        assert (
            all("(+3 more)" in line or "_PACT Act_" in line for line in title_lines)
            or len(title_lines) == 0
        )

    def test_exactly_five_signals_no_more_indicator(self):
        """Exactly 5 signals shows all without '+X more' indicator."""
        signals_by_state = {
            "Texas": [
                {"title": f"Signal {i}", "url": f"https://{i}.com", "program": "PACT Act"}
                for i in range(1, 6)  # Exactly 5 signals
            ]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # Should show count of 5
        assert "_PACT Act_ (5 signals)" in text

        # Should show all 5 signals
        for i in range(1, 6):
            assert f"Signal {i}" in text

        # Should NOT show '+X more' indicator
        assert "(+" not in text

    def test_missing_program_defaults_to_general(self):
        """Signals without program are grouped under 'General'."""
        signals_by_state = {
            "Texas": [
                {"title": "No program signal", "url": "https://example.com"},
                {"title": "Null program signal", "url": "https://example.com", "program": None},
                {"title": "Empty program signal", "url": "https://example.com", "program": ""},
            ]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # All should be under General
        assert "_General_ (3 signals)" in text

    def test_missing_url_no_link_format(self):
        """Signal without URL shows title without Slack link format."""
        signals_by_state = {
            "Texas": [
                {"title": "Signal without URL", "program": "PACT Act"},
                {"title": "Signal with empty URL", "url": "", "program": "PACT Act"},
            ]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # Should show titles without link format
        assert "Signal without URL" in text
        assert "Signal with empty URL" in text
        # Should not have Slack link format for these
        assert "<|Signal without URL>" not in text

    def test_missing_title_defaults_to_unknown(self):
        """Signal without title shows 'Unknown'."""
        signals_by_state = {
            "Texas": [
                {"url": "https://example.com", "program": "PACT Act"},
            ]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        assert "Unknown" in text

    def test_filters_out_empty_state_lists(self):
        """Empty state lists are filtered out."""
        signals_by_state = {
            "Texas": [{"title": "TX Signal", "url": "https://tx.com", "program": "General"}],
            "California": [],  # Empty - should be filtered
            "Florida": [],  # Empty - should be filtered
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # Texas should appear
        assert "*Texas*" in text
        # California and Florida should NOT appear
        assert "*California*" not in text
        assert "*Florida*" not in text

    def test_format_matches_design_spec(self):
        """Output matches the design spec example format."""
        signals_by_state = {
            "Texas": [
                {
                    "title": "Texas Veterans Commission suspends PACT Act outreach",
                    "url": "https://example.com/tx1",
                    "program": "PACT Act",
                },
                {
                    "title": "Texas expands toxic exposure screenings",
                    "url": "https://example.com/tx2",
                    "program": "PACT Act",
                },
                {
                    "title": "Community Care budget allocation update",
                    "url": "https://example.com/tx3",
                    "program": "Community Care",
                },
            ],
            "California": [
                {
                    "title": "CalVet reports on veteran services",
                    "url": "https://example.com/ca1",
                    "program": "PACT Act",
                },
            ],
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # Check structure
        lines = text.split("\n")

        # First line is header
        assert lines[0] == "*State Intelligence Weekly Digest*"
        # Second line is blank
        assert lines[1] == ""

        # California comes before Texas (alphabetical)
        assert text.find("*California*") < text.find("*Texas*")

        # Check PACT Act counts
        assert "_PACT Act_ (2 signals)" in text  # Texas has 2
        assert "_PACT Act_ (1 signal)" in text  # California has 1
        assert "_Community Care_ (1 signal)" in text  # Texas has 1

    def test_bullet_point_format(self):
        """Signal items use bullet point format with proper indentation."""
        signals_by_state = {
            "Texas": [{"title": "Test signal", "url": "https://example.com", "program": "General"}]
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # Check bullet point format with indentation
        assert "  \u2022 <https://example.com|Test signal>" in text

    def test_blank_lines_between_sections(self):
        """Blank lines separate programs and states."""
        signals_by_state = {
            "Texas": [
                {"title": "TX Signal 1", "url": "https://tx1.com", "program": "Program A"},
                {"title": "TX Signal 2", "url": "https://tx2.com", "program": "Program B"},
            ],
            "California": [
                {"title": "CA Signal", "url": "https://ca.com", "program": "Program C"},
            ],
        }

        result = format_state_digest(signals_by_state)

        assert result is not None
        text = result["text"]

        # There should be blank lines in the output (consecutive newlines)
        # The output should have structure with separations
        lines = text.split("\n")

        # Find blank lines (empty strings in the list)
        blank_line_count = lines.count("")
        assert blank_line_count >= 3  # At least: after header, between programs, between states
