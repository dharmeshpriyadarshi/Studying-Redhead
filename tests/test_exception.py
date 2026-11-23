import pytest

from src.exception import CustomException, error_message_detail


def test_exception_traceback_origin():
    def fail():
        return 1 / 0

    with pytest.raises(ZeroDivisionError) as exc:
        fail()
    wrapped = CustomException(exc.value)
    assert wrapped.original_error is exc.value
    assert "test_exception.py" in str(wrapped)
    assert "ZeroDivisionError" in str(wrapped)
    assert "division by zero" in str(wrapped)


def test_exception_without_traceback():
    detail = error_message_detail(ValueError("Example"))
    assert "Unknown" in detail
    assert "ValueError" in detail
    assert "Example" in detail
