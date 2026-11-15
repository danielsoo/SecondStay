"""Shared test setup: tests never reach the real Tiger Data service unless one asks for it."""

import os

import pytest


@pytest.fixture(autouse=True)
def no_tiger_database(request, monkeypatch):
    if request.node.get_closest_marker("tiger_service") and os.getenv("TIGER_TEST_DATABASE"):
        return
    from secondstay import tiger

    def refuse():
        raise tiger.NotConfigured("Tests run without the Tiger Data service.")

    monkeypatch.setattr(tiger, "database_url", refuse)
