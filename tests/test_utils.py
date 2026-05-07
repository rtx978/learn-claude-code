"""Tests for utility functions."""

import pytest
from utils import greet, validate_email, calculate_average, merge_dicts


class TestGreet:
    """Tests for the greet function."""

    def test_greet_basic(self):
        """Test basic greeting."""
        assert greet("Alice") == "Hello, Alice!"

    def test_greet_empty_name(self):
        """Test greeting with empty string."""
        assert greet("") == "Hello, !"


class TestValidateEmail:
    """Tests for the validate_email function."""

    def test_valid_email(self):
        """Test valid email addresses."""
        assert validate_email("user@example.com") is True
        assert validate_email("test.user@domain.org") is True

    def test_invalid_email(self):
        """Test invalid email addresses."""
        assert validate_email("invalid") is False
        assert validate_email("no@domain") is False
        assert validate_email("@nodomain.com") is False


class TestCalculateAverage:
    """Tests for the calculate_average function."""

    def test_average_basic(self):
        """Test basic average calculation."""
        assert calculate_average([1, 2, 3, 4, 5]) == 3.0

    def test_average_single_element(self):
        """Test average with single element."""
        assert calculate_average([5]) == 5.0

    def test_average_empty_list(self):
        """Test average with empty list."""
        assert calculate_average([]) is None

    def test_average_decimal_values(self):
        """Test average with decimal values."""
        assert calculate_average([1.5, 2.5, 3.0]) == pytest.approx(2.3333, rel=0.01)


class TestMergeDicts:
    """Tests for the merge_dicts function."""

    def test_merge_basic(self):
        """Test basic dictionary merge."""
        result = merge_dicts({"a": 1, "b": 2}, {"b": 3, "c": 4})
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_empty_dicts(self):
        """Test merging with empty dictionaries."""
        assert merge_dicts({}, {}) == {}
        assert merge_dicts({"a": 1}, {}) == {"a": 1}
        assert merge_dicts({}, {"b": 2}) == {"b": 2}