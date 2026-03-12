"""Tests for new_session_id() — time-sortable workspace naming."""

import re
import time
from datetime import UTC, datetime

from my_agent_core.session import new_session_id

SESSION_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")


class TestNewSessionId:
    def test_format(self):
        sid = new_session_id()
        assert SESSION_ID_PATTERN.match(sid), f"ID '{sid}' does not match expected format"

    def test_length(self):
        sid = new_session_id()
        assert len(sid) == 24  # YYYYMMDD(8) + -(1) + HHMMSS(6) + -(1) + hex8(8)

    def test_uniqueness(self):
        ids = [new_session_id() for _ in range(100)]
        assert len(set(ids)) == 100, "Duplicate session IDs detected"

    def test_utc_date_matches_today(self):
        today_utc = datetime.now(UTC).strftime("%Y%m%d")
        sid = new_session_id()
        assert sid.startswith(today_utc), f"ID '{sid}' does not start with today's UTC date {today_utc}"

    def test_lexicographic_order_equals_chronological(self):
        id1 = new_session_id()
        time.sleep(1.1)  # ensure a different second
        id2 = new_session_id()
        assert id1 < id2, f"Older ID '{id1}' should sort before newer ID '{id2}'"

    def test_parts_structure(self):
        sid = new_session_id()
        parts = sid.split("-")
        assert len(parts) == 3
        date_part, time_part, hex_part = parts
        assert len(date_part) == 8 and date_part.isdigit()
        assert len(time_part) == 6 and time_part.isdigit()
        assert len(hex_part) == 8 and all(c in "0123456789abcdef" for c in hex_part)

    def test_hex_suffix_is_lowercase(self):
        for _ in range(10):
            sid = new_session_id()
            hex_part = sid.split("-")[2]
            assert hex_part == hex_part.lower()
