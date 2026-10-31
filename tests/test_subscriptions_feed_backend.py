import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

import utils


@pytest.fixture
def backend(monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("offline placeholder", encoding="utf-8")
    monkeypatch.setattr(utils, "config_get", lambda key: str(cookies))
    monkeypatch.setattr(utils, "get_windows_region", lambda: "LY")
    monkeypatch.setattr(utils, "_", lambda message: f"localized:{message}")
    send = Mock(return_value={"videos": [], "continuation": None})
    monkeypatch.setattr(utils.deno_service, "send_command", send)
    # Every UI/install/prompt operation is forbidden even on an error path.
    for name in ("ensure_deno_installed", "ensure_cookies_configured"):
        monkeypatch.setattr(utils, name, Mock(side_effect=AssertionError(name)))
    for name in ("GetApp", "MessageBox", "CallAfter"):
        monkeypatch.setattr(utils.wx, name, Mock(side_effect=AssertionError(name)))
    yield send, cookies
    utils.ensure_deno_installed.assert_not_called()
    utils.ensure_cookies_configured.assert_not_called()
    utils.wx.GetApp.assert_not_called()
    utils.wx.MessageBox.assert_not_called()
    utils.wx.CallAfter.assert_not_called()


def assert_failure(result):
    assert result["videos"] == []
    assert result["continuation"] is None
    assert result["error"].startswith("localized:")
    assert "secret" not in result["error"]


@pytest.mark.parametrize("path_kind", ["unset", "missing", "directory"])
def test_subscriptions_require_existing_cookie_file(backend, monkeypatch, path_kind):
    send, cookies = backend
    value = {
        "unset": "",
        "missing": str(cookies.with_suffix(".absent")),
        "directory": str(cookies.parent),
    }[path_kind]
    monkeypatch.setattr(utils, "config_get", lambda key: value)
    assert_failure(utils.get_subscriptions_feed())
    send.assert_not_called()


@pytest.mark.parametrize("token", [None, "opaque+/=page-2"])
def test_subscriptions_rpc_auth_pagination_and_worker_safety(backend, token):
    send, cookies = backend
    send.return_value = {
        "videos": [
            {
                "id": "bbbbbbbbbbb",
                "title": "Newest",
                "author": "Channel",
                "published_time": "قبل ساعتين",
            },
            {"id": "aaaaaaaaaaa", "title": "Older", "published_time": "vor 3 Tagen"},
        ],
        "continuation": "opaque-next",
    }
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(utils.get_subscriptions_feed, token).result(timeout=3)
    assert [video["id"] for video in result["videos"]] == ["bbbbbbbbbbb", "aaaaaaaaaaa"]
    assert [video["published_time"] for video in result["videos"]] == [
        "قبل ساعتين",
        "vor 3 Tagen",
    ]
    assert result["continuation"] == "opaque-next"
    assert "error" not in result
    send.assert_called_once_with(
        "get_subscriptions_feed",
        {"cookiesPath": str(cookies), "location": "LY", "continuationToken": token},
    )


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        "secret",
        {},
        {"videos": None},
        {"videos": "secret"},
        {"error": "SAPISID=secret"},
        {"videos": [], "error": "secret"},
        {"videos": [], "continuation": {}},
        {"videos": [], "continuation": 1},
        {"videos": [], "continuation": " "},
        {"videos": [None, {}, "secret"]},
    ],
)
def test_subscriptions_malformed_and_rpc_errors_are_generic(backend, response, caplog):
    send, _ = backend
    send.return_value = response
    assert_failure(utils.get_subscriptions_feed())
    assert "secret" not in caplog.text


@pytest.mark.parametrize("failure_at", ["config", "rpc", "filesystem"])
def test_subscriptions_exceptions_are_sanitized(
    backend, monkeypatch, caplog, failure_at
):
    send, _ = backend
    failure = Mock(side_effect=RuntimeError("SAPISID=secret"))
    if failure_at == "config":
        monkeypatch.setattr(utils, "config_get", failure)
    elif failure_at == "filesystem":
        monkeypatch.setattr(utils.os.path, "isfile", failure)
    else:
        send.side_effect = failure.side_effect
    assert_failure(utils.get_subscriptions_feed())
    assert "secret" not in caplog.text


@pytest.mark.parametrize("token", [False, 1, {}, [], "", " "])
def test_subscriptions_reject_invalid_continuation_without_rpc(backend, token):
    send, _ = backend
    assert_failure(utils.get_subscriptions_feed(token))
    send.assert_not_called()


@pytest.mark.parametrize("token", [None, "next-video-page"])
def test_subscriptions_empty_page_retains_continuation(backend, token):
    send, _ = backend
    send.return_value = {"videos": [], "continuation": token}
    assert utils.get_subscriptions_feed() == send.return_value


def test_subscriptions_normalize_deduplicate_and_drop_private_fields(backend):
    send, _ = backend
    first = {
        "id": "a-b_c012345",
        "title": "Video",
        "author": None,
        "url": "https://private.invalid/secret",
        "published_time": {},
        "cookies": "secret",
        "is_live": "false",
        "metadata_text": ["Original text"],
    }
    send.return_value = {
        "videos": [
            first,
            {**first, "title": "Duplicate"},
            None,
            "secret",
            {},
            {"id": "PLplaylist", "title": "Playlist"},
            {"id": "bbbbbbbbbbb", "title": {"text": "Malformed"}},
        ],
        "continuation": None,
        "cookies": "secret",
    }
    result = utils.get_subscriptions_feed()
    assert result == {
        "videos": [
            {
                "id": "a-b_c012345",
                "title": "Video",
                "author": "",
                "url": "https://www.youtube.com/watch?v=a-b_c012345",
                "published_time": "",
                "is_live": False,
                "metadata_text": ["Original text"],
            }
        ],
        "continuation": None,
    }
    assert first["author"] is None
    assert "secret" not in str(result)


def test_subscriptions_offline_javascript_fixtures():
    """Run the repo's Deno.test fixture pattern with local build deps, no fetch."""
    root = Path(__file__).resolve().parents[1]
    dependency = (
        root / "build/js_service/node_modules/youtubei.js/dist/src/platform/node.js"
    )
    node = shutil.which("node")
    if node is None or not dependency.is_file():
        pytest.skip(
            "Offline JS fixtures require Node and installed build/js_service dependencies"
        )
    # Load unbundled service source without changing src's module resolution or
    # executing main(). The sole rewrites resolve its two local module imports.
    script = r"""
        import { readFileSync } from 'node:fs';
        const [servicePath, fixturePath, dependency] = JSON.parse(process.argv[1]);
        const service = readFileSync(servicePath, 'utf8')
            .replace("from 'youtubei.js'", `from '${dependency}'`);
        const serviceUrl = 'data:text/javascript;base64,' + Buffer.from(service).toString('base64');
        const fixture = readFileSync(fixturePath, 'utf8')
            .replace("from 'youtubei.js'", `from '${dependency}'`)
            .replace("from '../src/service.js'", `from '${serviceUrl}'`);
        const tests = [];
        globalThis.Deno = { test: (name, run) => tests.push({ name, run }) };
        globalThis.fetch = () => { throw new Error('Network forbidden in offline tests'); };
        await import('data:text/javascript;base64,' + Buffer.from(fixture).toString('base64'));
        for (const { name, run } of tests) {
            try { await run(); } catch (error) {
                console.error(name + ": " + error.message);
                process.exit(1);
            }
            console.log('PASS: ' + name);
        }
        if (!tests.length) throw new Error('No JS fixture tests registered');
    """
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            script,
            json.dumps(
                [
                    str(root / "src/service.js"),
                    str(root / "tests/test_subscriptions_feed_backend.js"),
                    dependency.as_uri(),
                ]
            ),
        ],
        check=False,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stdout + result.stderr[-12000:]
