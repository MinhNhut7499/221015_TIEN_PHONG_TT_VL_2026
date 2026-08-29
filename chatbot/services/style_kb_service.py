"""Open-vocabulary style knowledge-base service.

Loads the curated style knowledge base (``chatbot/knowledge/styles.json``) and
provides the "retrieval" layer of the open-vocabulary pipeline:

- normalise + match a free-text style name proposed by the VLM to a canonical
  KB entry (by name, alias, then fuzzy),
- build a top-K candidate set from a list of proposed names (padding with
  taxonomy siblings for coarse-to-fine breadth),
- render KB descriptions to inject into the panel/arbiter prompts,
- report names that fall OUTSIDE the KB so the caller can queue them for human
  review (the KB is never grown automatically at runtime).

The KB is a small in-memory structure (~100s of entries); matching is plain
string + ``difflib`` fuzzy comparison — no embeddings, no vector store.
"""
from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import zip_longest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.config import settings
from chatbot.utils.schemas import EvidenceItem, StyleEntry

logger = logging.getLogger(__name__)


@dataclass
class OovCandidate:
    """An out-of-KB (open-set) style cluster proposed by the VLMs.

    ``name`` is the chosen display spelling, ``votes`` the number of distinct
    sources (extraction calls / free read) that proposed any variant of it, and
    ``features`` the observed evidence-sheet feature strings that cited it (used
    to build a synthetic card so the judges have something to ground on).
    """

    name: str
    votes: int
    features: List[str] = field(default_factory=list)

# Words stripped from a style name before matching, so "Gothic architecture",
# "Gothic style" and "kiến trúc Gothic" all collapse to the same key.
_NOISE_TOKENS = (
    "architecture",
    "architectural",
    "style",
    "styles",
    "kiến trúc",
    "phong cách",
)


def _normalise(name: str) -> str:
    """Lower-case, strip punctuation/noise words, and collapse whitespace."""
    text = name.strip().lower()
    for token in _NOISE_TOKENS:
        text = text.replace(token, " ")
    for ch in "-_/,.()":
        text = text.replace(ch, " ")
    return " ".join(text.split())


# Generic words that carry little discriminative power for feature matching, so
# they are dropped before comparing observed evidence to a style's features.
_FEATURE_STOPWORDS = frozenset({
    "the", "and", "with", "for", "from", "into", "over", "under", "of", "a",
    "an", "or", "on", "in", "to", "by", "at", "is", "are", "its", "wide",
    "large", "small", "tall", "low", "high", "deep", "thick", "thin", "long",
    "wall", "walls", "roof", "roofs", "window", "windows", "door", "doors",
    "facade", "facades", "building", "structure", "form", "forms", "style",
    "decorative", "ornate", "ornament", "detail", "details", "stone", "brick",
})

# Minimum token-set Jaccard for an observed feature to count toward a style's
# feature-retrieval score (filters incidental single-word overlaps).
_FEATURE_MATCH_FLOOR = 0.34


def _feature_tokens(text: str) -> frozenset[str]:
    """Tokenise a feature phrase into a set of meaningful lowercased tokens."""
    cleaned = text.lower()
    for ch in "-_/,.()&;:":
        cleaned = cleaned.replace(ch, " ")
    return frozenset(
        tok
        for tok in cleaned.split()
        if len(tok) >= 3 and tok not in _FEATURE_STOPWORDS
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Token-set Jaccard overlap of two token sets (0.0 when either is empty)."""
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


class StyleKbService:
    """In-memory open-vocabulary architectural-style knowledge base."""

    def __init__(self, kb_path: str) -> None:
        """Load and index the KB file at ``kb_path``.

        Args:
            kb_path: Path to the styles.json knowledge base.

        Raises:
            FileNotFoundError: If the KB file does not exist.
            ValueError: If the KB JSON is malformed or has duplicate ids.
        """
        path = Path(kb_path)
        if not path.is_file():
            raise FileNotFoundError(f"Style KB not found at {kb_path!r}")
        raw = json.loads(path.read_text(encoding="utf-8"))

        self._families: Dict[str, dict] = raw.get("families", {})
        self._by_id: Dict[str, StyleEntry] = {}
        # Normalised name/alias → style id. First writer wins on collision.
        self._alias_index: Dict[str, str] = {}

        for item in raw.get("styles", []):
            entry = StyleEntry(**item)
            if entry.id in self._by_id:
                raise ValueError(f"Duplicate style id in KB: {entry.id!r}")
            self._by_id[entry.id] = entry
            for label in [entry.name, *entry.aliases]:
                key = _normalise(label)
                if key and key not in self._alias_index:
                    self._alias_index[key] = entry.id

        # Cache the list of normalised keys for fuzzy matching.
        self._alias_keys: List[str] = list(self._alias_index.keys())
        logger.info(
            "Loaded style KB: %d styles, %d families, %d alias keys",
            len(self._by_id),
            len(self._families),
            len(self._alias_keys),
        )

    # ── Basic accessors ──────────────────────────────────────────────────────

    def get(self, style_id: str) -> Optional[StyleEntry]:
        """Return the style entry with this id, or None."""
        return self._by_id.get(style_id)

    def all_styles(self) -> List[StyleEntry]:
        """Return every style entry in the KB."""
        return list(self._by_id.values())

    def all_names(self) -> List[str]:
        """Return the canonical display name of every style."""
        return [e.name for e in self._by_id.values()]

    def family_name(self, family_id: Optional[str]) -> Optional[str]:
        """Return the display name of a family id, or None."""
        if family_id and family_id in self._families:
            return self._families[family_id].get("name", family_id)
        return None

    # ── Matching ─────────────────────────────────────────────────────────────

    def match(self, name: str) -> Optional[StyleEntry]:
        """Match a free-text style name to a KB entry (exact → alias → fuzzy).

        Returns None when no confident match exists (caller should treat the
        name as out-of-KB and queue it for review).
        """
        key = _normalise(name)
        if not key:
            return None
        style_id = self._alias_index.get(key)
        if style_id is not None:
            return self._by_id[style_id]
        close = difflib.get_close_matches(
            key, self._alias_keys, n=1, cutoff=settings.KB_FUZZY_CUTOFF
        )
        if close:
            return self._by_id[self._alias_index[close[0]]]
        return None

    def resolve_card(self, name: str) -> Optional[StyleEntry]:
        """Resolve a name to a KB entry for display (looser than :meth:`match`).

        Tries the strict match first (exact → alias → fuzzy); if that fails,
        falls back to the nearest strongly name-related entry
        (:meth:`_name_neighbours`: substring containment or token Jaccard ≥ 0.5).
        This recovers display lookups for arbiter-generated names that drift from
        the canonical KB label (e.g. "Gothic Revival style" → "Gothic Revival")
        while staying name-grounded — it never invents an unrelated style.
        Returns None only when nothing is even name-related.
        """
        entry = self.match(name)
        if entry is not None:
            return entry
        neighbours = self._name_neighbours(name)
        return neighbours[0] if neighbours else None

    def _siblings(self, entry: StyleEntry) -> List[StyleEntry]:
        """Return other styles sharing the same parent family."""
        return [
            e
            for e in self._by_id.values()
            if e.parent == entry.parent and e.id != entry.id
        ]

    def styles_in_family(self, family_id: str) -> List[StyleEntry]:
        """Return every style whose ``parent`` is this family id.

        Used by the coarse-to-fine candidate channel (Phase 1a): once Agent A
        names a likely FAMILY (e.g. "islamic", "east-asian"), all of that
        family's styles are injected as candidates so the correct child style is
        guaranteed to be available even if no extraction call named it. The
        ``family_id`` is matched case-insensitively against both family ids and
        family display names, so a VLM that returns "Islamic" or "East Asian"
        still resolves.
        """
        key = family_id.strip().lower()
        if not key:
            return []
        # Resolve display name → family id (e.g. "east asian" → "east-asian").
        resolved = key if key in self._families else None
        if resolved is None:
            for fid, meta in self._families.items():
                if str(meta.get("name", "")).strip().lower() == key:
                    resolved = fid
                    break
        if resolved is None:
            return []
        return [e for e in self._by_id.values() if e.parent == resolved]

    def family_ids(self) -> List[str]:
        """Return all family ids (for prompt rendering / validation)."""
        return list(self._families.keys())

    def retrieve_by_features(
        self, observed_features: List[str], top_n: int
    ) -> List[StyleEntry]:
        """Rank KB entries by how well their features match observed evidence.

        The feature-based retrieval channel (Phase 1b): catches a style whose
        DEFINING FEATURES the VLM described but whose NAME it never proposed
        (e.g. it wrote "horseshoe arches" + "muqarnas vaults" but did not say
        "Moorish"). Each KB entry's ``defining_features`` and
        ``expected_profile`` values are compared phrase-by-phrase against the
        observed feature strings using token-set Jaccard; an entry scores the
        sum of its best per-observation matches above a small floor. Distinctive
        phrases (horseshoe / muqarnas / shikhara) dominate; generic ones
        (walls / roof) contribute little.

        Args:
            observed_features: Free-text feature strings from the evidence sheet.
            top_n: Maximum number of entries to return.

        Returns:
            Up to ``top_n`` entries with a positive match score, best first.
        """
        obs_token_sets = [t for f in observed_features if (t := _feature_tokens(f))]
        if not obs_token_sets:
            return []

        scored: List[Tuple[float, StyleEntry]] = []
        for entry in self._by_id.values():
            phrase_tokens = [
                t
                for phrase in [*entry.defining_features, *entry.expected_profile.values()]
                if (t := _feature_tokens(phrase))
            ]
            if not phrase_tokens:
                continue
            score = 0.0
            for obs in obs_token_sets:
                best = max(
                    (_jaccard(obs, pt) for pt in phrase_tokens), default=0.0
                )
                if best >= _FEATURE_MATCH_FLOOR:
                    score += best
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda s: s[0], reverse=True)
        return [e for _, e in scored[:top_n]]

    def _name_neighbours(self, name: str) -> List[StyleEntry]:
        """Find KB entries whose name is strongly related to a proposed name.

        Catches specific/parent variants the single exact match misses — e.g.
        a proposed "Spanish Colonial" also surfaces "Spanish Colonial Revival".
        Relatedness = normalised substring containment (either direction) OR
        token-set Jaccard ≥ 0.5. Excludes the exact same key; ordered by
        descending overlap. Generic single-token shares (e.g. only "revival")
        score below the cutoff and are not linked.
        """
        key = _normalise(name)
        if not key:
            return []
        key_tokens = set(key.split())
        scored: List[Tuple[float, StyleEntry]] = []
        for entry in self._by_id.values():
            best = 0.0
            for label in [entry.name, *entry.aliases]:
                ekey = _normalise(label)
                if not ekey or ekey == key:
                    continue
                etokens = set(ekey.split())
                union = key_tokens | etokens
                jaccard = len(key_tokens & etokens) / len(union) if union else 0.0
                score = 1.0 if (key in ekey or ekey in key) else jaccard
                best = max(best, score)
            if best >= 0.5:
                scored.append((best, entry))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [e for _, e in scored]

    def build_candidate_set(
        self, proposed_names: List[str], top_k: int
    ) -> Tuple[List[StyleEntry], List[str]]:
        """Resolve a single list of proposed names to a candidate set.

        Thin wrapper over :meth:`build_candidate_set_voted` with one extraction
        list and ``min_votes=1`` (every matched style is kept). See that method
        for the padding behaviour.

        Args:
            proposed_names: Free-text style names proposed by the VLM.
            top_k: Maximum number of candidate entries to return.

        Returns:
            (candidates, out_of_kb_names).
        """
        return self.build_candidate_set_voted([proposed_names], min_votes=1, top_k=top_k)

    def build_candidate_set_voted(
        self, proposed_lists: List[List[str]], min_votes: int, top_k: int
    ) -> Tuple[List[StyleEntry], List[str]]:
        """Vote proposed styles across several extraction calls into candidates.

        Each list is one extraction call's proposed styles. A style is matched to
        a KB id and gets one vote per list it appears in (deduped within a list,
        so a single call cannot vote twice). Styles with at least ``min_votes``
        votes become candidates, ordered by votes desc then first appearance —
        this filters one-off hallucinated names while keeping cross-call
        consensus. If the threshold would leave no candidates, it falls back to
        the union (``min_votes`` effectively 1) so the set is never empty.

        The set is then padded — first with strongly name-related KB entries
        (specific/parent variants of a near-miss proposal), then with taxonomy
        siblings — up to ``top_k``. Names that match no KB entry are returned
        separately for the suggestion queue.

        Args:
            proposed_lists: One list of proposed style names per extraction call.
            min_votes: Minimum number of calls a style must appear in to qualify.
            top_k: Maximum number of candidate entries to return.

        Returns:
            (candidates, out_of_kb_names).
        """
        votes, first_seen, out_of_kb, all_names = self._collect_votes(proposed_lists)
        selected = self._select_voted_ids(votes, first_seen, min_votes)

        candidates: List[StyleEntry] = [self._by_id[eid] for eid in selected]
        seen_ids: set[str] = set(selected)
        self._pad_candidates(candidates, seen_ids, all_names, top_k)
        return candidates[:top_k], out_of_kb

    def build_candidate_set_multi(
        self,
        proposed_lists: List[List[str]],
        observed_features: List[str],
        proposed_families: List[str],
        min_votes: int,
        top_k: int,
        feature_top_n: int,
    ) -> Tuple[List[StyleEntry], List[str]]:
        """Build candidates from THREE recall channels (Phase 1).

        Combines, in priority order, three independent ways the correct style can
        reach the candidate set — so it no longer depends on the VLM naming the
        style exactly:

        1. **Voted names** (existing): styles the extraction calls explicitly
           proposed, ranked by votes (the strongest signal).
        2. **Feature retrieval** (1b): styles whose KB defining-features match the
           OBSERVED evidence even if never named (``retrieve_by_features``).
        3. **Family expansion** (1a): every style of a family the VLM flagged
           (``styles_in_family``), guaranteeing the right child style is present
           once the coarser family is identified.

        Channels 1 and 2 are interleaved round-robin so a long voted list cannot
        starve the feature channel (and vice versa); family members fill any
        remaining room, then name-neighbour / sibling padding tops up to
        ``top_k``. Names matching no KB entry are returned for the suggestion
        queue (same as the voted path).

        Args:
            proposed_lists: One list of proposed style names per extraction call.
            observed_features: Free-text feature strings from the evidence sheet.
            proposed_families: Building-level family guesses (id or display name).
            min_votes: Minimum extraction calls a name must appear in to be a seed.
            top_k: Maximum number of candidates to return.
            feature_top_n: Max entries the feature channel may contribute.

        Returns:
            (candidates, out_of_kb_names).
        """
        votes, first_seen, out_of_kb, all_names = self._collect_votes(proposed_lists)
        voted_ids = self._select_voted_ids(votes, first_seen, min_votes)
        voted_entries = [self._by_id[eid] for eid in voted_ids]
        feature_entries = self.retrieve_by_features(observed_features, feature_top_n)

        merged: List[StyleEntry] = []
        seen_ids: set[str] = set()

        def _add(entry: StyleEntry) -> None:
            if entry.id not in seen_ids and len(merged) < top_k:
                seen_ids.add(entry.id)
                merged.append(entry)

        # Channels 1 + 2 interleaved so neither starves the other.
        for voted, feat in zip_longest(voted_entries, feature_entries):
            if len(merged) >= top_k:
                break
            if voted is not None:
                _add(voted)
            if feat is not None:
                _add(feat)

        # Channel 3: family members for breadth (coarse-to-fine).
        for family in proposed_families:
            if len(merged) >= top_k:
                break
            for entry in self.styles_in_family(family):
                _add(entry)

        # Final top-up with name-related variants then siblings.
        self._pad_candidates(merged, seen_ids, all_names, top_k)
        return merged[:top_k], out_of_kb

    def _collect_votes(
        self, proposed_lists: List[List[str]]
    ) -> Tuple[Dict[str, int], Dict[str, int], List[str], List[str]]:
        """Tally votes per KB id across extraction calls (one vote per call).

        Returns ``(votes, first_seen, out_of_kb, all_names)`` where ``votes`` maps
        KB id → number of calls it appeared in, ``first_seen`` maps id → first
        appearance order, ``out_of_kb`` lists deduped names matching no KB entry,
        and ``all_names`` is every proposed name (for neighbour padding).
        """
        votes: Dict[str, int] = {}
        first_seen: Dict[str, int] = {}
        out_of_kb: List[str] = []
        out_seen: set[str] = set()
        all_names: List[str] = []
        order = 0

        for proposed_names in proposed_lists:
            voted_in_list: set[str] = set()
            for name in proposed_names:
                all_names.append(name)
                entry = self.match(name)
                if entry is None:
                    cleaned, key = name.strip(), name.strip().lower()
                    if cleaned and key not in out_seen:
                        out_seen.add(key)
                        out_of_kb.append(cleaned)
                    continue
                if entry.id in voted_in_list:
                    continue  # one vote per extraction call
                voted_in_list.add(entry.id)
                votes[entry.id] = votes.get(entry.id, 0) + 1
                if entry.id not in first_seen:
                    first_seen[entry.id] = order
                    order += 1
        return votes, first_seen, out_of_kb, all_names

    def _select_voted_ids(
        self, votes: Dict[str, int], first_seen: Dict[str, int], min_votes: int
    ) -> List[str]:
        """Pick the seed ids meeting ``min_votes``, ranked by votes then order.

        Falls back to the union (every voted id) if the threshold would leave the
        seed set empty — the candidate set is never empty when any name matched.
        """
        selected = [eid for eid, n in votes.items() if n >= min_votes]
        if not selected:
            selected = list(votes.keys())
        selected.sort(key=lambda eid: (-votes[eid], first_seen[eid]))
        return selected

    def _pad_candidates(
        self,
        candidates: List[StyleEntry],
        seen_ids: set,
        all_names: List[str],
        top_k: int,
    ) -> None:
        """Top up ``candidates`` in place up to ``top_k``.

        First with strongly name-related KB entries (specific/parent variants of a
        near-miss proposal), then with taxonomy siblings for breadth.
        """
        if len(candidates) < top_k:
            for name in all_names:
                for neighbour in self._name_neighbours(name):
                    if len(candidates) >= top_k:
                        break
                    if neighbour.id not in seen_ids:
                        seen_ids.add(neighbour.id)
                        candidates.append(neighbour)
                if len(candidates) >= top_k:
                    break

        if len(candidates) < top_k:
            for entry in list(candidates):
                for sib in self._siblings(entry):
                    if len(candidates) >= top_k:
                        break
                    if sib.id not in seen_ids:
                        seen_ids.add(sib.id)
                        candidates.append(sib)
                if len(candidates) >= top_k:
                    break

    # ── Cross-extraction agreement ───────────────────────────────────────────

    def extraction_agreement(self, proposed_lists: List[List[str]]) -> Optional[float]:
        """Measure how much several extraction calls agree on the proposed styles.

        Each list is one extraction call's proposed style names. They are mapped
        to KB-id SETS (via :meth:`match`, so synonyms collapse to one id and
        out-of-KB names are dropped — consistent with the vote-by-id grounding).
        Returns the mean pairwise Jaccard overlap of those id sets, the natural
        counterpart to the panel's mean pairwise Spearman: high → the calls saw
        the same styles (stable, single-style image); low → the calls disagreed
        (multi-style / hybrid / ambiguous image).

        Args:
            proposed_lists: One list of proposed style names per extraction call.

        Returns:
            Mean pairwise Jaccard in [0.0, 1.0]; ``None`` when it cannot be
            defined — fewer than two lists resolve to a non-empty KB-id set.
        """
        id_sets: List[set] = []
        for names in proposed_lists:
            ids = {entry.id for name in names if (entry := self.match(name))}
            if ids:
                id_sets.append(ids)
        if len(id_sets) < 2:
            return None

        overlaps: List[float] = []
        for i in range(len(id_sets)):
            for j in range(i + 1, len(id_sets)):
                union = id_sets[i] | id_sets[j]
                overlaps.append(len(id_sets[i] & id_sets[j]) / len(union))
        return round(sum(overlaps) / len(overlaps), 4)

    # ── Out-of-KB clustering (open-set escape) ───────────────────────────────

    def cluster_out_of_kb(
        self,
        proposed_lists: List[List[str]],
        min_votes: int,
        evidence_items: Optional[List["EvidenceItem"]] = None,
    ) -> List[OovCandidate]:
        """Cluster proposed style names that match NO KB entry into candidates.

        Only names that :meth:`match` cannot resolve are considered. Variants of
        the same style ("Metabolism" / "Metabolist architecture") are grouped by
        their normalised key (exact, then fuzzy ≥ 0.9) so they form ONE cluster
        rather than competing as separate names. Each source list (extraction
        call / free read) contributes at most one vote per cluster. Clusters with
        at least ``min_votes`` votes are returned, most-voted first; the display
        name is the most frequent surface spelling.

        When ``evidence_items`` is given, each cluster's ``features`` is filled
        with the observed feature strings whose ``suggested_styles`` point at it
        (the synthetic-card material that lets the judges ground on something).

        Args:
            proposed_lists: One list of proposed style names per source.
            min_votes: Minimum distinct sources a cluster must appear in.
            evidence_items: Optional evidence-sheet items to attach features from.

        Returns:
            Out-of-KB candidate clusters meeting the vote threshold.
        """
        # cluster key (a representative normalised string) → aggregate state.
        keys: List[str] = []
        votes: Dict[str, int] = {}
        order: Dict[str, int] = {}
        surface_counts: Dict[str, Dict[str, int]] = {}
        next_order = 0

        def _resolve_key(norm: str, create: bool) -> Optional[str]:
            """Find the cluster key for ``norm`` (exact then fuzzy); ``norm`` if new.

            When ``create`` is False, returns an existing key only (no new cluster)
            — used when attaching features so an unrelated feature does not spawn a
            cluster.
            """
            if norm in votes:
                return norm
            close = difflib.get_close_matches(norm, keys, n=1, cutoff=0.9)
            if close:
                return close[0]
            return norm if create else None

        for names in proposed_lists:
            counted: set[str] = set()  # one vote per source per cluster
            for raw in names:
                if self.match(raw) is not None:
                    continue  # in-KB names are handled by the voted channel
                norm = _normalise(raw)
                if not norm:
                    continue
                key = _resolve_key(norm, create=True)
                if key not in votes:
                    votes[key] = 0
                    order[key] = next_order
                    next_order += 1
                    surface_counts[key] = {}
                    keys.append(key)
                surface = raw.strip()
                surface_counts[key][surface] = surface_counts[key].get(surface, 0) + 1
                if key not in counted:
                    counted.add(key)
                    votes[key] += 1

        selected = [k for k in keys if votes[k] >= min_votes]
        selected.sort(key=lambda k: (-votes[k], order[k]))

        features_by_key: Dict[str, List[str]] = {k: [] for k in selected}
        if evidence_items:
            selected_set = set(selected)
            for item in evidence_items:
                for suggested in item.suggested_styles:
                    norm = _normalise(suggested)
                    if not norm:
                        continue
                    key = _resolve_key(norm, create=False)
                    if key in selected_set and item.feature:
                        feats = features_by_key[key]
                        if item.feature not in feats:
                            feats.append(item.feature)

        clusters: List[OovCandidate] = []
        for key in selected:
            display = max(surface_counts[key].items(), key=lambda kv: kv[1])[0]
            clusters.append(
                OovCandidate(name=display, votes=votes[key],
                             features=features_by_key.get(key, []))
            )
        return clusters

    # ── Prompt rendering ─────────────────────────────────────────────────────

    def descriptions_for(self, entries: List[StyleEntry]) -> str:
        """Render a candidate block for injection into panel/arbiter prompts."""
        lines: List[str] = []
        for e in entries:
            family = self.family_name(e.parent)
            header = f"- {e.name}"
            meta = ", ".join(part for part in [family, *e.region, e.period] if part)
            if meta:
                header += f" ({meta})"
            lines.append(header)
            if e.defining_features:
                lines.append(f"    defining features: {'; '.join(e.defining_features)}")
            if e.expected_profile:
                profile = "; ".join(f"{k}={v}" for k, v in e.expected_profile.items())
                lines.append(f"    expected: {profile}")
        return "\n".join(lines)


@lru_cache(maxsize=4)
def get_style_kb(kb_path: Optional[str] = None) -> StyleKbService:
    """Return a cached StyleKbService for the given path (default from settings)."""
    return StyleKbService(kb_path or settings.STYLE_KB_PATH)
