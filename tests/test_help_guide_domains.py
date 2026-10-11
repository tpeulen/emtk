"""A tour card or help window of one domain still shows text another registered catalogue translates."""

from __future__ import annotations

from emtk import i18n
from emtk.help_guide import EmTkGuidedTour, _tr


def test_a_named_domain_falls_back_to_the_other_registered_catalogues():
    i18n.add_translations("de", {"Load a file": "Datei laden"}, domain="shared")
    i18n.add_translations("de", {"Own text": "Eigener Text"}, domain="mine")
    i18n.set_language("de")
    try:
        assert i18n.tr("Load a file", domain="mine") == "Load a file"
        assert _tr("Load a file", "mine") == "Datei laden"
        assert _tr("Own text", "mine") == "Eigener Text"
        assert _tr("Never translated anywhere", "mine") == "Never translated anywhere"
        tour = EmTkGuidedTour([{"title": "Load a file", "text": "x"}], domain="mine")
        assert _tr(tour.steps[0]["title"], tour.domain) == "Datei laden"
    finally:
        i18n.set_language("en")
