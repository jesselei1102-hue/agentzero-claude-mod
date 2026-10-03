"""Pure external scorer: compare a run result YAML to an Answer key."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from score.yamlio import load_mapping


class UnsignedAnswerKeyError(ValueError):
    """Raised when scoring is asked to use an Answer key that is not operator-signed."""


@dataclass(frozen=True)
class Totals:
    matched: int
    items: int


@dataclass(frozen=True)
class Score:
    run_id: str
    total: Totals
    categories: dict[str, Totals]
    hold_out: Totals


def score_run(answer_key_path: Path, run_result_path: Path) -> Score:
    """Score a run result against an Answer key. Hold-out items are totalled separately."""
    answer_key = load_mapping(answer_key_path)
    _require_model(answer_key)
    run_result = load_mapping(run_result_path)
    run_id = run_result.get("run_id")
    if not run_id:
        raise ValueError("run result YAML must include run_id")

    key_items = answer_key.get("items") or []
    _require_signed(key_items)
    run_by_id = {item["id"]: item for item in run_result.get("items") or [] if "id" in item}

    visible_matched: dict[str, list[bool]] = {}
    hold_out_hits: list[bool] = []

    for key_item in key_items:
        item_id = key_item["id"]
        matched = _item_matches(key_item, run_by_id.get(item_id))
        if key_item.get("hold_out"):
            hold_out_hits.append(matched)
            continue
        category = key_item["category"]
        visible_matched.setdefault(category, []).append(matched)

    all_visible = [hit for hits in visible_matched.values() for hit in hits]
    return Score(
        run_id=str(run_id),
        total=_totals(all_visible),
        categories={name: _totals(hits) for name, hits in visible_matched.items()},
        hold_out=_totals(hold_out_hits),
    )


def no_lower(later: Score, earlier: Score) -> bool:
    """True iff later is no lower than earlier on total, every category, and hold-out."""
    if later.total.matched < earlier.total.matched:
        return False
    if later.hold_out.matched < earlier.hold_out.matched:
        return False
    names = set(earlier.categories) | set(later.categories)
    for name in names:
        later_matched = later.categories.get(name, Totals(0, 0)).matched
        earlier_matched = earlier.categories.get(name, Totals(0, 0)).matched
        if later_matched < earlier_matched:
            return False
    return True


def write_score(score: Score, destination: Path) -> None:
    """Write a Score YAML record keyed by run id."""
    payload: dict[str, Any] = {
        "run_id": score.run_id,
        "total": asdict(score.total),
        "categories": {name: asdict(totals) for name, totals in score.categories.items()},
        "hold_out": asdict(score.hold_out),
    }
    destination.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _require_model(answer_key: dict[str, Any]) -> None:
    model = answer_key.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError(
            "Answer key must include model referencing the operator's fixed Revit model"
        )


def _require_signed(items: list[Any]) -> None:
    unsigned = [
        item.get("id", "<missing id>")
        for item in items
        if item.get("signed_off") is not True
    ]
    if unsigned:
        raise UnsignedAnswerKeyError(
            "Answer key is unsigned; scored runs require signed_off: true on every item "
            f"(unsigned: {', '.join(str(item_id) for item_id in unsigned)})"
        )


def _totals(hits: list[bool]) -> Totals:
    return Totals(matched=sum(hits), items=len(hits))


def _item_matches(key_item: dict[str, Any], run_item: dict[str, Any] | None) -> bool:
    if run_item is None:
        return False
    observed_ok = str(run_item.get("observed")) == str(key_item["observed"])
    result_ok = _pass_fail(run_item.get("result")) == _pass_fail(key_item["result"])
    return observed_ok and result_ok


def _pass_fail(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)
