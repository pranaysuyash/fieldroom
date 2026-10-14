import pytest

from pdf_field_lab.config import positive_int_env


def test_positive_int_env_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("PDF_FIELD_LAB_TEST_LIMIT", raising=False)

    assert positive_int_env("PDF_FIELD_LAB_TEST_LIMIT", 12) == 12


def test_positive_int_env_reads_positive_override(monkeypatch):
    monkeypatch.setenv("PDF_FIELD_LAB_TEST_LIMIT", "2048")

    assert positive_int_env("PDF_FIELD_LAB_TEST_LIMIT", 12) == 2048


@pytest.mark.parametrize("raw_value", ["not-a-number", "0", "-1"])
def test_positive_int_env_rejects_invalid_or_nonpositive_values(monkeypatch, raw_value):
    monkeypatch.setenv("PDF_FIELD_LAB_TEST_LIMIT", raw_value)

    with pytest.raises(ValueError, match="PDF_FIELD_LAB_TEST_LIMIT must be a positive integer"):
        positive_int_env("PDF_FIELD_LAB_TEST_LIMIT", 12)


def test_positive_int_env_rejects_invalid_default():
    with pytest.raises(ValueError, match="default for PDF_FIELD_LAB_TEST_LIMIT"):
        positive_int_env("PDF_FIELD_LAB_TEST_LIMIT", 0)
