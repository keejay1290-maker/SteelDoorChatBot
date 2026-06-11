"""Regression tests for BUG-001 (name extraction) and BUG-002 (£k budget parser)."""
from app.chat import _extract_fields
from app.session import ConversationSession


# ---------------------------------------------------------------------------
# BUG-001 — name extraction
# ---------------------------------------------------------------------------

def _fresh() -> ConversationSession:
    return ConversationSession()


def test_name_from_my_name_is():
    s = _extract_fields("My name is John Smith", _fresh())
    assert s.name == "John Smith"


def test_name_from_im():
    s = _extract_fields("I'm Sarah Jones and I need a double door", _fresh())
    assert s.name == "Sarah Jones"


def test_name_from_its_for():
    s = _extract_fields("It's for Michael Brown", _fresh())
    assert s.name == "Michael Brown"


def test_name_stopword_not_captured():
    # "I'm looking" — "looking" is in stopwords, should NOT be set as name
    s = _extract_fields("I'm looking for an external door", _fresh())
    assert s.name is None


def test_name_stopword_single_not_captured():
    # "I'm single" — door spec word, not a name
    s = _extract_fields("I'm single door type please", _fresh())
    assert s.name is None


def test_name_lowercased_input_title_cased():
    # Text arrives lowercased (via _normalise_text) — should still extract and title-case
    s = _extract_fields("it's for dave jones", _fresh())
    assert s.name == "Dave Jones"


def test_name_not_overwritten():
    s = _fresh()
    s.name = "Existing Name"
    s = _extract_fields("My name is Different Person", s)
    assert s.name == "Existing Name"


# ---------------------------------------------------------------------------
# BUG-002 — budget parser
# ---------------------------------------------------------------------------

def test_budget_pound_k():
    s = _extract_fields("My budget is £8k", _fresh())
    assert s.budget_min == 8000.0


def test_budget_plain_k():
    # "8k budget" — previously failed because \d[\d,]+ requires 2+ digits
    s = _extract_fields("8k budget", _fresh())
    assert s.budget_min == 8000.0


def test_budget_range_k():
    s = _extract_fields("budget is £4k-£6k", _fresh())
    assert s.budget_min == 4000.0
    assert s.budget_max == 6000.0


def test_budget_full_amount():
    s = _extract_fields("I have £12,000 to spend", _fresh())
    assert s.budget_min == 12000.0


def test_budget_range_full():
    s = _extract_fields("budget £4,000-£6,000", _fresh())
    assert s.budget_min == 4000.0
    assert s.budget_max == 6000.0


def test_budget_number_before_keyword():
    s = _extract_fields("12000 budget", _fresh())
    assert s.budget_min == 12000.0


def test_budget_single_digit_k():
    # "5k budget"
    s = _extract_fields("5k budget", _fresh())
    assert s.budget_min == 5000.0
