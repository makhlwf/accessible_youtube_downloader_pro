import json
from types import SimpleNamespace
from unittest.mock import Mock

import paths
import utils


def test_get_youtubei_version_prefers_lock_resolution(tmp_path, monkeypatch):
    lock_path = tmp_path / "deno.lock"
    config_path = tmp_path / "deno.json"
    lock_path.write_text(
        json.dumps(
            {
                "version": "5",
                "specifiers": {"npm:youtubei.js@^17.0.1": "17.2.0"},
                "npm": {"youtubei.js@17.2.0": {}},
            }
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps({"imports": {"youtubei.js": "npm:youtubei.js@^17.0.1"}}),
        encoding="utf-8",
    )

    def runtime_file(name):
        return str(lock_path if name == "deno.lock" else config_path)

    monkeypatch.setattr(paths, "get_js_runtime_lock_path", lambda: str(lock_path))
    monkeypatch.setattr(paths, "get_js_runtime_config_path", lambda: str(config_path))
    monkeypatch.setattr(paths, "get_js_runtime_file", runtime_file)

    assert utils.get_youtubei_version() == "17.2.0"


def test_get_youtubei_version_falls_back_to_config(tmp_path, monkeypatch):
    lock_path = tmp_path / "missing.lock"
    config_path = tmp_path / "deno.json"
    config_path.write_text(
        json.dumps({"imports": {"youtubei.js": "npm:youtubei.js@^17.0.1"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "get_js_runtime_lock_path", lambda: str(lock_path))
    monkeypatch.setattr(paths, "get_js_runtime_config_path", lambda: str(config_path))

    assert utils.get_youtubei_version() == "17.0.1"


def test_js_runtime_lock_path_stays_with_override_config(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "js_runtime"
    main_dir = tmp_path / "src"
    runtime_dir.mkdir()
    main_dir.mkdir()
    (runtime_dir / "deno.json").write_text(
        json.dumps({"imports": {"youtubei.js": "npm:youtubei.js@17.2.0"}}),
        encoding="utf-8",
    )
    (main_dir / "deno.lock").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(paths, "js_runtime_path", str(runtime_dir))
    monkeypatch.setattr(paths, "main_path", str(main_dir))

    assert paths.get_js_runtime_lock_path() == str(runtime_dir / "deno.lock")


def test_install_youtubei_version_writes_runtime_config_and_refreshes_cache(
    tmp_path, monkeypatch
):
    runtime_dir = tmp_path / "js_runtime"
    service_script = tmp_path / "service.js"
    deno_path = tmp_path / "deno.exe"
    service_script.write_text("import 'youtubei.js';\n", encoding="utf-8")
    deno_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(paths, "js_runtime_path", str(runtime_dir))
    monkeypatch.setattr(paths, "deno_path", str(deno_path))
    monkeypatch.setattr(paths, "main_path", str(tmp_path))
    monkeypatch.setattr(
        paths, "get_js_runtime_service_script", lambda: str(service_script)
    )

    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    stop = Mock()
    monkeypatch.setattr(utils.subprocess, "run", run)
    monkeypatch.setattr(utils.deno_service, "stop", stop)
    monkeypatch.setattr(utils.wx, "MessageBox", Mock())

    assert utils.install_youtubei_version("17.2.0")

    config = json.loads((runtime_dir / "deno.json").read_text(encoding="utf-8"))
    assert config == {"imports": {"youtubei.js": "npm:youtubei.js@17.2.0"}}
    assert run.call_args.args[0][:5] == [
        str(deno_path),
        "cache",
        "--config",
        str(runtime_dir / "deno.json"),
        "--lock",
    ]
    assert f"--reload=npm:{utils.YOUTUBEI_PACKAGE}" in run.call_args.args[0]
    stop.assert_called_once()


def test_update_youtubei_skips_when_current_is_latest(monkeypatch):
    message_box = Mock(return_value=utils.wx.OK)
    install = Mock()
    monkeypatch.setattr(utils, "get_youtubei_version", lambda: "17.2.0")
    monkeypatch.setattr(
        utils, "get_latest_npm_package_version", lambda package: "17.2.0"
    )
    monkeypatch.setattr(utils.wx, "MessageBox", message_box)
    monkeypatch.setattr(utils, "install_youtubei_version", install)

    assert utils.update_youtubei()

    install.assert_not_called()
    assert "أحدث إصدار" in message_box.call_args.args[0]
