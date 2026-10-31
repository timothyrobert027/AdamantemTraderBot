import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from adamantem.data import histdata

PAGE = """<html><form id="file_down" name="file_down" target="_self" action="get.php" method="POST">
<input type="hidden" name="tk" id="tk" value="abc123"/>
<input type="hidden" name="date" id="date" value="2023"/>
<input type="hidden" name="datemonth" id="datemonth" value="2023"/>
<input type="hidden" name="platform" id="platform" value="ASCII"/>
<input type="hidden" name="timeframe" id="timeframe" value="M1"/>
<input type="hidden" name="fxpair" id="fxpair" value="XAUUSD"/>
</form></html>"""

CSV = (
    "20230102 180000;1826.250000;1827.140000;1825.980000;1826.400000;0\n"
    "20230102 180100;1826.400000;1826.900000;1826.100000;1826.700000;0\n"
)


def _zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("DAT_ASCII_XAUUSD_M1_2023.csv", text)
    return buf.getvalue()


def test_form_fields():
    f = histdata.form_fields(PAGE)
    assert f["tk"] == "abc123" and f["fxpair"] == "XAUUSD" and f["datemonth"] == "2023"


def test_form_missing_raises():
    with pytest.raises(histdata.HistDataError):
        histdata.form_fields("<html>nothing</html>")


def test_parse_zip_converts_est_to_utc():
    df = histdata.parse_zip(_zip(CSV))
    assert df.index[0] == pd.Timestamp("2023-01-02 23:00", tz="UTC")
    assert list(df.iloc[0]) == [1826.25, 1827.14, 1825.98, 1826.40]


def test_download_builds_ask_from_assumed_spread(tmp_path, monkeypatch):
    def fake_request(url, data=None, referer=None):
        return PAGE.encode() if data is None else _zip(CSV)

    monkeypatch.setattr(histdata, "_request", fake_request)
    monkeypatch.setattr(histdata.time, "sleep", lambda s: None)
    m1 = histdata.download_m1("XAUUSD", date(2023, 1, 1), date(2023, 2, 1), tmp_path, 0.3)
    assert len(m1) == 2
    assert ((m1.ask_close - m1.bid_close).round(6) == 0.3).all()
    assert (tmp_path / "XAUUSD_2023.zip").exists()  # cached for the next run
