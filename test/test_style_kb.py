"""Tests for the open-vocabulary style knowledge-base service."""
import pytest

from chatbot.services.style_kb_service import StyleKbService, _normalise
from chatbot.utils.schemas import StyleEntry


@pytest.fixture(scope="module")
def kb() -> StyleKbService:
    """Load the real KB once for the module."""
    return StyleKbService("chatbot/knowledge/styles.json")


def test_kb_loads_styles_and_families(kb: StyleKbService) -> None:
    """KB loads a non-trivial number of styles and families."""
    styles = kb.all_styles()
    assert len(styles) >= 100
    assert all(isinstance(s, StyleEntry) for s in styles)
    # Every style points at a known family.
    fam_ids = set(kb._families.keys())
    assert all(s.parent in fam_ids for s in styles)


def test_match_exact_name(kb: StyleKbService) -> None:
    """Exact canonical name matches its entry."""
    entry = kb.match("Gothic")
    assert entry is not None
    assert entry.id == "gothic"


def test_match_is_case_and_suffix_insensitive(kb: StyleKbService) -> None:
    """Matching ignores case and noise words like 'architecture'/'style'."""
    assert kb.match("gothic architecture").id == "gothic"  # type: ignore[union-attr]
    assert kb.match("  BAROQUE Style ").id == "baroque"     # type: ignore[union-attr]


def test_match_alias(kb: StyleKbService) -> None:
    """An alias resolves to the canonical entry."""
    entry = kb.match("Neo-Gothic")
    assert entry is not None
    assert entry.id == "gothic-revival"


def test_match_fuzzy_typo(kb: StyleKbService) -> None:
    """A small typo still resolves via fuzzy matching."""
    entry = kb.match("Brutalsim")  # transposed letters
    assert entry is not None
    assert entry.id == "brutalism"


def test_match_unknown_returns_none(kb: StyleKbService) -> None:
    """A clearly out-of-KB name returns None (not a wrong guess)."""
    assert kb.match("Klingon Imperial Architecture") is None


def test_build_candidate_set_dedups_and_caps(kb: StyleKbService) -> None:
    """Candidate set dedups, resolves names, and respects top_k."""
    candidates, out_of_kb = kb.build_candidate_set(
        ["Gothic", "gothic architecture", "Baroque", "Mughal"], top_k=8
    )
    ids = [c.id for c in candidates]
    assert "gothic" in ids and "baroque" in ids and "mughal" in ids
    assert ids.count("gothic") == 1  # deduped
    assert len(candidates) <= 8
    assert out_of_kb == []


def test_build_candidate_set_reports_out_of_kb(kb: StyleKbService) -> None:
    """Names with no KB match are reported for the suggestion queue."""
    candidates, out_of_kb = kb.build_candidate_set(
        ["Gothic", "Totally Made Up Style"], top_k=8
    )
    assert any(c.id == "gothic" for c in candidates)
    assert "Totally Made Up Style" in out_of_kb


def test_build_candidate_set_pads_to_top_k_with_relatives(kb: StyleKbService) -> None:
    """A single match is padded with name-related variants/siblings up to top_k."""
    candidates, _ = kb.build_candidate_set(["Gothic"], top_k=5)
    assert len(candidates) == 5
    assert candidates[0].id == "gothic"
    ids = {c.id for c in candidates}
    # Name-related Gothic variants are pulled in for breadth.
    assert "venetian-gothic" in ids or "brick-gothic" in ids


def test_build_candidate_set_surfaces_specific_revival_variant(kb: StyleKbService) -> None:
    """A near-variant proposal surfaces the specific KB style (regression).

    Ground truth was Spanish Colonial Revival but it never reached the panel.
    Proposing the near name 'Spanish Colonial' must now pull the precise
    'Spanish Colonial Revival' entry into the candidate set.
    """
    candidates, _ = kb.build_candidate_set(["Spanish Colonial"], top_k=8)
    names = {c.name for c in candidates}
    assert "Spanish Colonial Revival" in names


def test_voted_candidate_set_drops_one_off_styles(kb: StyleKbService) -> None:
    """min_votes=2 keeps styles seen in ≥2 calls and drops one-off names."""
    calls = [
        ["Gothic", "Baroque"],
        ["Gothic", "Renaissance"],
        ["Gothic", "Baroque"],
        ["Mughal"],  # one-off
    ]
    candidates, _ = kb.build_candidate_set_voted(calls, min_votes=2, top_k=8)
    ids = [c.id for c in candidates]
    # Gothic (3) and Baroque (2) survive; Mughal (1) is filtered out of the seeds.
    assert ids[0] == "gothic"  # most-voted leads
    assert "baroque" in ids
    assert "mughal" not in ids[:2]  # not a voted seed (may appear only via padding)


def test_voted_candidate_set_counts_synonyms_once_per_call(kb: StyleKbService) -> None:
    """Different spellings of one style across calls count toward the same id."""
    calls = [
        ["Neo-Gothic"],       # alias of gothic-revival
        ["Gothic Revival"],   # canonical name of gothic-revival
        ["Baroque"],
    ]
    candidates, _ = kb.build_candidate_set_voted(calls, min_votes=2, top_k=8)
    ids = [c.id for c in candidates]
    # gothic-revival got 2 votes via two spellings → it leads; Baroque (1) does not qualify.
    assert ids[0] == "gothic-revival"


def test_voted_candidate_set_falls_back_to_union_when_empty(kb: StyleKbService) -> None:
    """If the threshold filters everything, fall back to the union (never empty)."""
    calls = [["Gothic"], ["Baroque"], ["Renaissance"]]  # all one-off
    candidates, _ = kb.build_candidate_set_voted(calls, min_votes=3, top_k=8)
    ids = {c.id for c in candidates}
    assert {"gothic", "baroque", "renaissance"} <= ids


def test_descriptions_for_renders_features(kb: StyleKbService) -> None:
    """Rendered candidate block includes name and defining features."""
    gothic = kb.get("gothic")
    assert gothic is not None
    block = kb.descriptions_for([gothic])
    assert "Gothic" in block
    assert "defining features:" in block


def test_styles_in_family_by_id(kb: StyleKbService) -> None:
    """All styles of a family resolve by family id (coarse-to-fine 1a)."""
    islamic = {e.id for e in kb.styles_in_family("islamic")}
    assert {"moorish", "ottoman", "mughal"} <= islamic
    # Every returned entry actually belongs to the family.
    assert all(e.parent == "islamic" for e in kb.styles_in_family("islamic"))


def test_styles_in_family_by_display_name(kb: StyleKbService) -> None:
    """A family display name (e.g. 'East Asian') resolves like its id."""
    by_name = {e.id for e in kb.styles_in_family("East Asian")}
    by_id = {e.id for e in kb.styles_in_family("east-asian")}
    assert by_name == by_id and by_name


def test_styles_in_family_unknown_is_empty(kb: StyleKbService) -> None:
    """An unknown family returns an empty list (no crash)."""
    assert kb.styles_in_family("nonexistent") == []
    assert kb.styles_in_family("") == []


def test_retrieve_by_features_surfaces_unnamed_style(kb: StyleKbService) -> None:
    """Distinctive observed features rank the right style first without its name.

    The VLM may describe Moorish features ('horseshoe arches', 'muqarnas')
    without ever proposing the name 'Moorish'; feature retrieval must still
    surface it (Phase 1b — the recall channel the KB was built for).
    """
    observed = [
        "horseshoe and polylobed arches",
        "muqarnas vaults",
        "zellij tilework",
        "intricate carved stucco",
    ]
    results = kb.retrieve_by_features(observed, top_n=5)
    assert results, "expected at least one feature match"
    assert results[0].id == "moorish"


def test_retrieve_by_features_empty_input(kb: StyleKbService) -> None:
    """No observed features → no results (no crash)."""
    assert kb.retrieve_by_features([], top_n=5) == []
    assert kb.retrieve_by_features(["the and of"], top_n=5) == []  # all stopwords


def test_build_candidate_set_multi_recovers_via_features(kb: StyleKbService) -> None:
    """Feature + family channels surface the right style even when names are wrong.

    Agent A names the WRONG styles (Byzantine/Gothic) but DESCRIBES Moorish
    features and guesses the Islamic family. The multichannel builder must still
    place Moorish in the candidate set (Phase 1 recall fix).
    """
    proposed_lists = [["Byzantine", "Gothic"], ["Byzantine"]]
    observed = [
        "horseshoe and polylobed arches",
        "muqarnas vaults",
        "zellij tilework",
    ]
    candidates, _ = kb.build_candidate_set_multi(
        proposed_lists, observed_features=observed, proposed_families=["Islamic"],
        min_votes=1, top_k=12, feature_top_n=6,
    )
    ids = {c.id for c in candidates}
    assert "moorish" in ids                       # via feature retrieval
    assert any(c.parent == "islamic" for c in candidates)  # via family expansion


def test_build_candidate_set_multi_keeps_voted_names(kb: StyleKbService) -> None:
    """Voted name candidates are still included alongside the new channels."""
    candidates, _ = kb.build_candidate_set_multi(
        [["Gothic"], ["Gothic"]], observed_features=["pointed lancet arches"],
        proposed_families=[], min_votes=1, top_k=12, feature_top_n=6,
    )
    assert any(c.id == "gothic" for c in candidates)
    assert len(candidates) <= 12


def test_normalise_helper() -> None:
    """The normaliser strips case, punctuation and noise tokens."""
    assert _normalise("Gothic Architecture") == "gothic"
    assert _normalise("Art-Nouveau style") == "art nouveau"


def test_extraction_agreement_identical_lists_is_one(kb: StyleKbService) -> None:
    """Extraction calls proposing the same styles fully agree (Jaccard 1.0)."""
    calls = [["Gothic", "Baroque"], ["Gothic", "Baroque"]]
    assert kb.extraction_agreement(calls) == 1.0


def test_extraction_agreement_disjoint_lists_is_zero(kb: StyleKbService) -> None:
    """Extraction calls with no style in common have zero overlap."""
    calls = [["Gothic"], ["Baroque"]]
    assert kb.extraction_agreement(calls) == 0.0


def test_extraction_agreement_counts_synonyms_as_agreement(kb: StyleKbService) -> None:
    """Different spellings of one style count as agreement (mapped by KB id)."""
    calls = [["Neo-Gothic"], ["Gothic Revival"]]  # both → gothic-revival
    assert kb.extraction_agreement(calls) == 1.0


def test_extraction_agreement_ignores_out_of_kb_names(kb: StyleKbService) -> None:
    """Out-of-KB names are dropped before measuring overlap."""
    calls = [["Gothic", "Totally Made Up Style"], ["Gothic"]]
    # Both resolve to {gothic}; the junk name is ignored → full agreement.
    assert kb.extraction_agreement(calls) == 1.0


def test_extraction_agreement_none_with_fewer_than_two_sets(kb: StyleKbService) -> None:
    """Undefined when fewer than two lists resolve to a non-empty KB-id set."""
    assert kb.extraction_agreement([["Gothic"]]) is None
    assert kb.extraction_agreement([["Gothic"], ["Totally Made Up Style"]]) is None
    assert kb.extraction_agreement([]) is None


def test_extraction_agreement_partial_overlap(kb: StyleKbService) -> None:
    """Mean pairwise Jaccard reflects partial style overlap across calls."""
    calls = [["Gothic", "Baroque"], ["Gothic", "Renaissance"]]
    # intersection {gothic} = 1, union {gothic, baroque, renaissance} = 3 → 1/3.
    assert kb.extraction_agreement(calls) == round(1 / 3, 4)
