import random

import pytest

from pbb.engine.cards import DECK, Deal, deal_from_seed, deal_seed, parse_card, shuffled_deck


def test_deck_is_52_unique():
    assert len(DECK) == 52 == len(set(DECK))


@pytest.mark.parametrize("raw,want", [("Ah", "Ah"), ("ah", "Ah"), ("tD", "Td"), ("2c", "2c")])
def test_parse_card(raw, want):
    assert parse_card(raw) == want


@pytest.mark.parametrize("raw", ["", "A", "Ahh", "1h", "Ax", "10h", None, 5])
def test_parse_card_rejects(raw):
    with pytest.raises(ValueError):
        parse_card(raw)


def test_shuffle_is_seeded_and_complete():
    assert shuffled_deck(7) == shuffled_deck(7)
    assert shuffled_deck(7) != shuffled_deck(8)
    assert sorted(shuffled_deck(7)) == sorted(DECK)


def test_deal_has_nine_distinct_cards():
    d = deal_from_seed(123)
    assert isinstance(d, Deal)
    cards = d.button_hole + d.bb_hole + d.board
    assert len(cards) == 9 == len(set(cards))


def test_deal_seed_is_stable_and_spread():
    assert deal_seed(1, 0) == deal_seed(1, 0)
    seeds = {deal_seed(1, i) for i in range(500)} | {deal_seed(2, i) for i in range(500)}
    assert len(seeds) == 1000


def test_global_rng_untouched():
    random.seed(99)
    expected = random.random()
    random.seed(99)
    deal_from_seed(5)
    assert random.random() == expected
