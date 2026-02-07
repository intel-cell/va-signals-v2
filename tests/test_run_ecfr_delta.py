from unittest.mock import MagicMock, patch

import pytest

from src.run_ecfr_delta import TITLES, build_parser, run_ecfr_delta


class TestTitlesDict:
    def test_contains_title_38(self):
        assert "38" in TITLES

    def test_contains_title_5(self):
        assert "5" in TITLES

    def test_contains_title_20(self):
        assert "20" in TITLES

    def test_title_38_fields(self):
        t = TITLES["38"]
        assert t["doc_id"] == "ECFR-title38.xml"
        assert "title-38" in t["url"]
        assert t["source_id"] == "govinfo_ecfr_title_38"

    def test_title_5_fields(self):
        t = TITLES["5"]
        assert t["doc_id"] == "ECFR-title5.xml"
        assert "title-5" in t["url"]
        assert t["source_id"] == "govinfo_ecfr_title_5"

    def test_title_20_fields(self):
        t = TITLES["20"]
        assert t["doc_id"] == "ECFR-title20.xml"
        assert "title-20" in t["url"]
        assert t["source_id"] == "govinfo_ecfr_title_20"

    def test_all_titles_have_required_keys(self):
        for num, info in TITLES.items():
            assert "doc_id" in info, f"Title {num} missing doc_id"
            assert "url" in info, f"Title {num} missing url"
            assert "name" in info, f"Title {num} missing name"
            assert "source_id" in info, f"Title {num} missing source_id"


class TestCLI:
    def test_default_is_title_38(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.title == "38"
        assert args.all_titles is False

    def test_title_5(self):
        parser = build_parser()
        args = parser.parse_args(["--title", "5"])
        assert args.title == "5"

    def test_title_20(self):
        parser = build_parser()
        args = parser.parse_args(["--title", "20"])
        assert args.title == "20"

    def test_title_38_explicit(self):
        parser = build_parser()
        args = parser.parse_args(["--title", "38"])
        assert args.title == "38"

    def test_all_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--all"])
        assert args.all_titles is True

    def test_invalid_title_rejected(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--title", "99"])


class TestRunEcfrDelta:
    @patch("src.run_ecfr_delta.send_error_alert")
    @patch("src.run_ecfr_delta.insert_source_run")
    @patch("src.run_ecfr_delta.validate")
    @patch("src.run_ecfr_delta.upsert_ecfr_seen", return_value=True)
    @patch("src.run_ecfr_delta.init_db")
    @patch("src.run_ecfr_delta.requests.head")
    @patch("src.run_ecfr_delta.load_run_schema", return_value={})
    @patch("src.run_ecfr_delta.write_run_record")
    def test_title_38_default(
        self,
        mock_write,
        mock_schema,
        mock_head,
        mock_init_db,
        mock_upsert,
        mock_validate,
        mock_insert,
        mock_alert,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Last-Modified": "Thu, 01 Jan 2026", "ETag": '"abc"'}
        mock_head.return_value = mock_resp

        result = run_ecfr_delta()
        assert result["source_id"] == "govinfo_ecfr_title_38"
        assert result["status"] == "SUCCESS"
        mock_upsert.assert_called_once()
        assert mock_upsert.call_args[0][0] == "ECFR-title38.xml"

    @patch("src.run_ecfr_delta.send_error_alert")
    @patch("src.run_ecfr_delta.insert_source_run")
    @patch("src.run_ecfr_delta.validate")
    @patch("src.run_ecfr_delta.upsert_ecfr_seen", return_value=True)
    @patch("src.run_ecfr_delta.init_db")
    @patch("src.run_ecfr_delta.requests.head")
    @patch("src.run_ecfr_delta.load_run_schema", return_value={})
    @patch("src.run_ecfr_delta.write_run_record")
    def test_title_5(
        self,
        mock_write,
        mock_schema,
        mock_head,
        mock_init_db,
        mock_upsert,
        mock_validate,
        mock_insert,
        mock_alert,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Last-Modified": "Thu, 01 Jan 2026", "ETag": '"def"'}
        mock_head.return_value = mock_resp

        result = run_ecfr_delta("5")
        assert result["source_id"] == "govinfo_ecfr_title_5"
        assert result["status"] == "SUCCESS"
        assert mock_upsert.call_args[0][0] == "ECFR-title5.xml"

    @patch("src.run_ecfr_delta.send_error_alert")
    @patch("src.run_ecfr_delta.insert_source_run")
    @patch("src.run_ecfr_delta.validate")
    @patch("src.run_ecfr_delta.upsert_ecfr_seen", return_value=True)
    @patch("src.run_ecfr_delta.init_db")
    @patch("src.run_ecfr_delta.requests.head")
    @patch("src.run_ecfr_delta.load_run_schema", return_value={})
    @patch("src.run_ecfr_delta.write_run_record")
    def test_title_20(
        self,
        mock_write,
        mock_schema,
        mock_head,
        mock_init_db,
        mock_upsert,
        mock_validate,
        mock_insert,
        mock_alert,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Last-Modified": "Thu, 01 Jan 2026", "ETag": '"ghi"'}
        mock_head.return_value = mock_resp

        result = run_ecfr_delta("20")
        assert result["source_id"] == "govinfo_ecfr_title_20"
        assert result["status"] == "SUCCESS"
        assert mock_upsert.call_args[0][0] == "ECFR-title20.xml"

    @patch("src.run_ecfr_delta.send_error_alert")
    @patch("src.run_ecfr_delta.insert_source_run")
    @patch("src.run_ecfr_delta.validate")
    @patch("src.run_ecfr_delta.upsert_ecfr_seen", return_value=False)
    @patch("src.run_ecfr_delta.init_db")
    @patch("src.run_ecfr_delta.requests.head")
    @patch("src.run_ecfr_delta.load_run_schema", return_value={})
    @patch("src.run_ecfr_delta.write_run_record")
    def test_no_change_returns_no_data(
        self,
        mock_write,
        mock_schema,
        mock_head,
        mock_init_db,
        mock_upsert,
        mock_validate,
        mock_insert,
        mock_alert,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Last-Modified": "old", "ETag": '"same"'}
        mock_head.return_value = mock_resp

        result = run_ecfr_delta("38")
        assert result["status"] == "NO_DATA"

    @patch("src.run_ecfr_delta.send_error_alert")
    @patch("src.run_ecfr_delta.insert_source_run")
    @patch("src.run_ecfr_delta.validate")
    @patch("src.run_ecfr_delta.upsert_ecfr_seen")
    @patch("src.run_ecfr_delta.init_db")
    @patch("src.run_ecfr_delta.requests.head")
    @patch("src.run_ecfr_delta.load_run_schema", return_value={})
    @patch("src.run_ecfr_delta.write_run_record")
    def test_http_error_returns_error(
        self,
        mock_write,
        mock_schema,
        mock_head,
        mock_init_db,
        mock_upsert,
        mock_validate,
        mock_insert,
        mock_alert,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_head.return_value = mock_resp

        result = run_ecfr_delta("38")
        assert result["status"] == "ERROR"
        assert len(result["errors"]) == 1
        mock_alert.assert_called_once()
