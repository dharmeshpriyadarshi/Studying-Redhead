from pathlib import Path
from traceback import extract_tb


def error_message_detail(error: Exception) -> str:
    """Extract the original failure location and error details."""

    traceback_frames = extract_tb(error.__traceback__)

    if traceback_frames:
        frame = traceback_frames[-1]
        file_name = Path(frame.filename).name
        line_number = frame.lineno
    else:
        file_name = "Unknown"
        line_number = "Unknown"

    return (
        f"Error occurred in script [{file_name}] "
        f"at line [{line_number}] "
        f"with error [{type(error).__name__}]: {error}"
    )


class CustomException(Exception):
    """Base exception for Studying Redhead."""

    def __init__(self, error: Exception):
        self.original_error = error
        self.error_message = error_message_detail(error)

        super().__init__(self.error_message)

    def __str__(self) -> str:
        return self.error_message