import browser_extension_manager as manager


def test_sync_browser_extension_files_refreshes_user_copy(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled" / "browser_extension"
    user_settings = tmp_path / "settings"
    user_extension = user_settings / "browser_extension"
    bundled.mkdir(parents=True)
    user_extension.mkdir(parents=True)
    (bundled / "manifest.json").write_text('{"version": "2"}', encoding="utf-8")
    (bundled / "background.js").write_text("new", encoding="utf-8")
    (user_extension / "background.js").write_text("old", encoding="utf-8")
    (user_extension / "removed.js").write_text("stale", encoding="utf-8")

    monkeypatch.setattr(manager.paths, "get_bundled_data_path", lambda: str(tmp_path / "bundled"))
    monkeypatch.setattr(manager.paths, "settings_path", str(user_settings))

    assert manager.sync_browser_extension_files() == str(user_extension)
    assert (user_extension / "background.js").read_text(encoding="utf-8") == "new"
    assert not (user_extension / "removed.js").exists()


def test_sync_browser_extension_files_returns_empty_when_bundled_copy_is_missing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(manager.paths, "get_bundled_data_path", lambda: str(tmp_path))
    monkeypatch.setattr(manager.paths, "settings_path", str(tmp_path / "settings"))

    assert manager.sync_browser_extension_files() == ""
