import hashlib
import io
import sys
import zipfile
from unittest.mock import MagicMock

import pytest

from download_handler import aria2


@pytest.mark.parametrize("archive_matches_checksum", [True, False])
def test_windows_aria2_setup_verifies_archive_before_install(
    monkeypatch, tmp_path, archive_matches_checksum
):
    bits = 64 if sys.maxsize > 2**32 else 32
    asset = f"aria2-{aria2._RELEASE}-win-{bits}bit-build1"
    binary = b"test aria2 binary"
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(f"{asset}/aria2c.exe", binary)
    contents = data.getvalue()
    digest = hashlib.sha256(contents if archive_matches_checksum else b"").hexdigest()
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [contents]
    request = MagicMock(return_value=response)

    monkeypatch.setattr(aria2.sys, "platform", "win32")
    monkeypatch.setattr(aria2.paths, "settings_path", str(tmp_path))
    monkeypatch.setitem(aria2._ARCHIVES, bits, digest)
    monkeypatch.setattr(aria2.requests, "get", request)

    target = tmp_path / "aria2" / f"{aria2._RELEASE}-{bits}" / "aria2c.exe"
    check_cancelled = MagicMock()
    announce = MagicMock()
    if archive_matches_checksum:
        assert aria2._get_executable(check_cancelled, announce) == str(target)
        assert target.read_bytes() == binary
        assert aria2._get_executable(check_cancelled, announce) == str(target)
    else:
        with pytest.raises(ValueError, match="checksum"):
            aria2._get_executable(check_cancelled, announce)
        assert not target.exists()
    request.assert_called_once()
    announce.assert_called_once()
