"""External scorer: Answer key + run result YAML → Score. Never agent self-assessment."""

from score.draft import draft_answer_key
from score.scorer import Score, Totals, UnsignedAnswerKeyError, no_lower, score_run, write_score

__all__ = [
    "Score",
    "Totals",
    "UnsignedAnswerKeyError",
    "draft_answer_key",
    "no_lower",
    "score_run",
    "write_score",
]
