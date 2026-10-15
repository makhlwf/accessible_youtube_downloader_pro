import os
from unittest.mock import Mock

import deno_service
import paths
import utils


def test_youtube_service_path_discovery(monkeypatch, tmp_path):
    exe_name = "youtube_service.exe" if os.name == "nt" else "youtube_service"
    service_file = tmp_path / exe_name
    service_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(paths, "settings_path", str(tmp_path))
    found = paths.get_youtube_service_path()
    assert found == str(service_file)


def test_get_quickjs_path_discovery(monkeypatch, tmp_path):
    exe_name = "qjs.exe" if os.name == "nt" else "qjs"
    qjs_file = tmp_path / exe_name
    qjs_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(paths, "settings_path", str(tmp_path))
    found = paths.get_quickjs_path()
    assert found == str(qjs_file)


def test_configured_js_runtimes_prefers_quickjs_and_deno(monkeypatch):
    monkeypatch.setattr(paths, "get_quickjs_path", lambda: "/opt/qjs")
    monkeypatch.setattr(paths, "get_deno_path", lambda: "/opt/deno")
    monkeypatch.setattr(os.path, "exists", lambda p: True)

    runtimes = utils.get_configured_js_runtimes()
    assert "quickjs" in runtimes
    assert runtimes["quickjs"]["path"] == "/opt/qjs"
    assert "deno" in runtimes
    assert runtimes["deno"]["path"] == "/opt/deno"


def test_ensure_deno_installed_returns_true_when_youtube_service_present(monkeypatch):
    monkeypatch.setattr(
        paths, "get_youtube_service_path", lambda: "/bin/youtube_service"
    )
    monkeypatch.setattr(os.path, "exists", lambda p: p == "/bin/youtube_service")

    assert utils.ensure_deno_installed() is True
    assert utils.check_deno() is True


def test_deno_service_starts_standalone_youtube_service(monkeypatch):
    monkeypatch.setattr(
        paths, "get_youtube_service_path", lambda: "/bin/youtube_service"
    )
    process = Mock()
    popen = Mock(return_value=process)
    monkeypatch.setattr(deno_service.subprocess, "Popen", popen)
    monkeypatch.setattr(deno_service.threading, "Thread", Mock())

    service = deno_service.DenoService()
    service._ensure_process()

    assert popen.call_args.args[0] == ["/bin/youtube_service"]
    service.stop()


def test_get_youtube_service_version(monkeypatch):
    from types import SimpleNamespace

    run = Mock(
        return_value=SimpleNamespace(
            returncode=0, stdout="youtube_service 1.0.0\n", stderr=""
        )
    )
    monkeypatch.setattr(
        paths, "get_youtube_service_path", lambda: "/bin/youtube_service"
    )
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    monkeypatch.setattr(utils.subprocess, "run", run)

    version = utils.get_youtube_service_version()
    assert version == "v1.0.0"


def test_download_youtube_service(tmp_path, monkeypatch):
    install_target = tmp_path / "youtube_service.exe"
    monkeypatch.setattr(paths, "youtube_service_install_path", str(install_target))

    def fake_dialog(*args, **kwargs):
        install_target.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr("gui.update_dialog.UpdateDialog", fake_dialog)

    assert utils.download_youtube_service() is True
    assert install_target.is_file()


def test_update_youtube_service_skips_when_latest(monkeypatch):
    monkeypatch.setattr(utils, "get_youtube_service_version", lambda: "v1.0.0")
    monkeypatch.setattr(utils, "get_latest_github_release", lambda repo: "v1.0.0")
    message_box = Mock(return_value=utils.wx.OK)
    monkeypatch.setattr(utils.wx, "MessageBox", message_box)

    assert utils.update_youtube_service() is True
    assert "أحدث إصدار" in message_box.call_args.args[0]


def test_cli_update_youtube_service(tmp_path, monkeypatch):
    import cli.deps as cli_deps

    target = tmp_path / "youtube_service.exe"
    monkeypatch.setattr(paths, "youtube_service_install_path", str(target))
    monkeypatch.setattr(utils, "get_youtube_service_version", lambda: "v1.0.0")
    monkeypatch.setattr(utils, "get_latest_github_release", lambda repo: "v1.0.1")

    def fake_download(url, dest):
        with open(dest, "w", encoding="utf-8") as f:
            f.write("binary")

    monkeypatch.setattr(cli_deps, "_http_download", fake_download)
    ok, msg = cli_deps.update_youtube_service()
    assert ok is True
    assert "تم تحديث" in msg
    assert target.is_file()
