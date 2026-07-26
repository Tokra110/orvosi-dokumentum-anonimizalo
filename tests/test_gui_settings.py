import json


def test_update_config_is_read_modify_write(tmp_path, monkeypatch):
    from gui import settings

    cfg_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "CONFIG_PATH", cfg_path)

    settings.update_config(last_dir="/a")
    settings.update_config(output_mode="folder")

    data = json.loads(cfg_path.read_text())
    assert data == {"last_dir": "/a", "output_mode": "folder"}


def test_load_config_tolerates_corrupt_file(tmp_path, monkeypatch):
    from gui import settings

    cfg_path = tmp_path / "settings.json"
    cfg_path.write_text("{not json")
    monkeypatch.setattr(settings, "CONFIG_PATH", cfg_path)

    assert settings.load_config() == {}


def test_sanitize_log_strips_paths_and_filenames():
    from gui.settings import sanitize_log

    msg = "Saved: /home/user/Documents/leletek/Kiss Pál lelet.md from 'Kiss Pál.pdf'"
    out = sanitize_log(msg)
    assert "/home/user" not in out
    assert "Kiss Pál lelet.md" not in out
    assert "XYZ.md" in out and "XYZ.pdf" in out


def test_last_dir_falls_back_to_home(tmp_path, monkeypatch):
    from gui import settings

    monkeypatch.setattr(settings, "CONFIG_PATH", tmp_path / "settings.json")
    settings.update_config(last_dir=str(tmp_path / "does-not-exist"))
    from pathlib import Path

    assert settings.get_last_dir() == str(Path.home())
