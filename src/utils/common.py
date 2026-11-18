import pickle
import yaml
from pathlib import Path
from typing import Any

from src.logger import logger
from src.exception import CustomException


ROOT_DIR = Path(__file__).resolve().parents[2]


def resolve_path(file_path: str | Path) -> Path:
    """Resolve relative paths against the project root."""

    path = Path(file_path)

    if not path.is_absolute():
        path = ROOT_DIR / path

    return path.resolve()


def read_yaml(path_to_yaml: str | Path) -> dict:
    """Safely load a YAML configuration file."""

    try:
        path = resolve_path(path_to_yaml)

        with path.open("r", encoding="utf-8") as file:
            content = yaml.safe_load(file)

        if not isinstance(content, dict):
            raise ValueError(
                "YAML configuration must contain a mapping."
            )

        logger.info("YAML configuration loaded from: %s", path)
        return content

    except Exception as error:
        raise CustomException(error) from error


def save_object(file_path: str | Path, obj: Any) -> None:
    """Serialize a Python object to a local file."""

    try:
        path = resolve_path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("wb") as file:
            pickle.dump(obj, file, protocol=pickle.HIGHEST_PROTOCOL)

        logger.info("Object serialized and saved at: %s", path)

    except Exception as error:
        raise CustomException(error) from error


def load_object(file_path: str | Path) -> Any:
    """Deserialize an object from a trusted local file only."""

    try:
        path = resolve_path(file_path)

        if not path.is_file():
            raise FileNotFoundError(
                f"Artifact does not exist: {path}"
            )

        with path.open("rb") as file:
            obj = pickle.load(file)

        logger.info("Object deserialized from: %s", path)
        return obj

    except Exception as error:
        raise CustomException(error) from error