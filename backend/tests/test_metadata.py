"""Tests des fonctions pures de métadonnées (slug, coercition de valeurs)."""

from chatbot.data import metadata


def test_slugify_strips_accents_and_punct():
    assert metadata.slugify("Type d'habitation") == "type_d_habitation"
    assert metadata.slugify("Puissance thermique à Tbase / 35") == (
        "puissance_thermique_a_tbase_35"
    )
    assert metadata.slugify("SCOP déclaré basse température") == (
        "scop_declare_basse_temperature"
    )


def test_dedup_suffixes_collisions():
    assert metadata._dedup(["a", "a", "b", "a"]) == ["a", "a_2", "b", "a_3"]


def test_logement_id_keeps_leading_zeros():
    assert metadata._logement_id("Log. 002026") == "002026"


def test_coerce_numbers_strings_and_missing():
    assert metadata._coerce("167.98") == 167.98
    assert metadata._coerce("12,5") == 12.5  # virgule décimale FR
    assert metadata._coerce("air/eau") == "air/eau"
    assert metadata._coerce("-") is None
    assert metadata._coerce(None) is None
