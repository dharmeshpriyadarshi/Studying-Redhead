import pytest

from src.exception import CustomException
from src.utils.common import resolve_path, read_yaml, save_object, load_object


def test_resolve_path(isolated_root):
    expected = isolated_root / "configs/config.yaml"
    assert resolve_path("configs/config.yaml") == expected.resolve()
    assert resolve_path(expected) == expected.resolve()


def test_yaml_mapping(isolated_root):
    path = isolated_root / "configs/test.yaml"
    path.write_text("project:\n  name: Studying Redhead\n", encoding="utf-8")
    assert read_yaml(path) == {"project": {"name": "Studying Redhead"}}


@pytest.mark.parametrize("content", ["- one\n- two\n", "[broken", ""])
def test_invalid_yaml(isolated_root, content):
    path = isolated_root / "configs/bad.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CustomException):
        read_yaml(path)


def test_missing_yaml():
    with pytest.raises(CustomException) as exc:
        read_yaml("configs/missing.yaml")
    assert isinstance(exc.value.original_error, FileNotFoundError)


def test_pickle_round_trip(isolated_root):
    path = "artifacts/nested/example.pkl"
    original = {"planet": "Mars", "tile_size": 256}
    save_object(path, original)
    assert (isolated_root / path).is_file()
    assert load_object(path) == original


def test_missing_pickle():
    with pytest.raises(CustomException):
        load_object("artifacts/missing.pkl")
