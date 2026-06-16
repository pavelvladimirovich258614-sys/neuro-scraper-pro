"""Тесты эвристики определения пола по имени."""

import pytest

from services.telethon_core import TelethonCore

tc = TelethonCore()


@pytest.mark.parametrize("name", ["Мария", "Анна", "Елена", "Ольга", "Татьяна", "Анастасия"])
def test_female_names(name):
    assert tc._detect_gender(name) == "F"


@pytest.mark.parametrize("name", ["Александр", "Сергей", "Дмитрий", "Иван", "Михаил"])
def test_male_names(name):
    assert tc._detect_gender(name) == "M"


@pytest.mark.parametrize("name", ["Никита", "Илья", "Данила", "Лёша", "Саша"])
def test_male_exceptions_on_a_ya_endings(name):
    # Мужские имена с женскими окончаниями не должны определяться как F
    assert tc._detect_gender(name) == "M"


def test_female_by_ending():
    # Незнакомое имя с женским окончанием
    assert tc._detect_gender("Снежана") == "F"


def test_empty_name_unknown():
    assert tc._detect_gender(None) == "неизвестно"
    assert tc._detect_gender("") == "неизвестно"
