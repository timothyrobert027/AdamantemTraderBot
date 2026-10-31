import lzma
import urllib.error
from datetime import date

import pytest

from adamantem.data import dukascopy
from adamantem.data.dukascopy import RECORD, IncompleteDownload, download_m1


def _day_bytes(price: int) -> bytes:
    recs = [(60, price, price + 500, price - 500, price + 1000, 2.0)]
    return lzma.compress(b"".join(RECORD.pack(*r) for r in recs), format=lzma.FORMAT_ALONE)


def test_download_resumes_from_cache(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(url, dest, retries=4):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_day_bytes(2000_000 if "BID" in url else 2000_200))

    monkeypatch.setattr(dukascopy, "_fetch", fake_fetch)
    m1 = download_m1("XAUUSD", date(2024, 1, 2), date(2024, 1, 4), tmp_path, pause_s=0)
    assert len(calls) == 4 and len(m1) == 2
    assert (m1.ask_close - m1.bid_close > 0).all()
    download_m1("XAUUSD", date(2024, 1, 2), date(2024, 1, 4), tmp_path, pause_s=0)
    assert len(calls) == 4  # second run served from cache


def test_download_stops_cleanly_when_server_fails(tmp_path, monkeypatch):
    def failing_fetch(url, dest, retries=4):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(dukascopy, "_fetch", failing_fetch)
    with pytest.raises(IncompleteDownload) as info:
        download_m1("XAUUSD", date(2024, 1, 1), date(2024, 1, 31), tmp_path, pause_s=0,
                    max_consecutive_failures=3)
    assert info.value.done == 0 and "not responding" in info.value.reason
