"""Тесты CLI-вывода."""

import pytest
from vagus.layer3.cli.utils.output import (
    print_dict,
    print_error,
    print_info,
    print_success,
    print_table,
)


def test_print_table(capsys):
    print_table("Test", ["Col1", "Col2"], [["a", "b"], ["c", "d"]])
    out = capsys.readouterr().out
    assert "a" in out or "Col1" in out


def test_print_dict(capsys):
    print_dict("Test Dict", {"key": "value"})
    out = capsys.readouterr().out
    assert "key" in out or "value" in out


def test_print_success(capsys):
    print_success("ok!")
    out = capsys.readouterr().out
    assert "ok!" in out


def test_print_error(capsys):
    print_error("fail!")
    out = capsys.readouterr().out
    assert "fail!" in out


def test_print_info(capsys):
    print_info("info!")
    out = capsys.readouterr().out
    assert "info!" in out
