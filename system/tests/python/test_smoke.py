def test_fixture_vault_has_notes(vault):
    assert (vault / "wiki" / "Index.md").is_file()
    assert (vault / "wiki" / "work" / "concepts" / "Kafka.md").is_file()


def test_vaultlib_importable():
    import vaultlib  # noqa: F401
