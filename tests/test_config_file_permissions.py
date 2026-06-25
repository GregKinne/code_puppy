import configparser
import os

from code_puppy import config as cp_config


def _isolated_config(monkeypatch, tmp_path):
    config_dir = tmp_path / ".config" / "code_puppy"
    config_file = config_dir / "puppy.cfg"
    data_dir = tmp_path / ".local" / "share" / "code_puppy"
    cache_dir = tmp_path / ".cache" / "code_puppy"
    state_dir = tmp_path / ".local" / "state" / "code_puppy"

    monkeypatch.setattr(cp_config, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(cp_config, "CONFIG_FILE", str(config_file))
    monkeypatch.setattr(cp_config, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(cp_config, "CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cp_config, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(cp_config, "SKILLS_DIR", str(data_dir / "skills"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir, config_file


def _write_lax_config(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser()
    parser[cp_config.DEFAULT_SECTION] = {"model_settings_demo_temperature": "0.1"}
    with open(path, "w", encoding="utf-8") as f:
        parser.write(f)
    os.chmod(path, 0o666)


def test_set_config_value_writes_private_config(monkeypatch, tmp_path):
    _, config_file = _isolated_config(monkeypatch, tmp_path)

    cp_config.set_config_value("model", "gpt-test")

    assert config_file.exists()
    assert config_file.stat().st_mode & 0o777 == 0o600


def test_reset_value_repairs_existing_lax_config(monkeypatch, tmp_path):
    _, config_file = _isolated_config(monkeypatch, tmp_path)
    _write_lax_config(config_file)

    cp_config.reset_value("model_settings_demo_temperature")

    assert config_file.stat().st_mode & 0o777 == 0o600


def test_set_model_name_repairs_existing_lax_config(monkeypatch, tmp_path):
    _, config_file = _isolated_config(monkeypatch, tmp_path)
    _write_lax_config(config_file)

    cp_config.set_model_name("gpt-test")

    assert config_file.stat().st_mode & 0o777 == 0o600


def test_clear_model_settings_repairs_existing_lax_config(monkeypatch, tmp_path):
    _, config_file = _isolated_config(monkeypatch, tmp_path)
    _write_lax_config(config_file)

    cp_config.clear_model_settings("demo")

    assert config_file.stat().st_mode & 0o777 == 0o600
