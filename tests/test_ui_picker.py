"""Customer picker: a customer ID typed straight into the dropdown is resolved without the search box."""
import pytest

ui = pytest.importorskip("frontend.utils.ui")


def test_typed_id_resolves_any_case(container):
    assert ui._resolve_typed_customer(container, "DEMO-A-LOYAL") == "DEMO-A-LOYAL"
    assert ui._resolve_typed_customer(container, "  demo-a-loyal ") == "DEMO-A-LOYAL"


def test_typed_partial_text_uses_first_match(container):
    assert ui._resolve_typed_customer(container, "DEMO-D") in {"DEMO-D-OVERDUE", "DEMO-D1-OVERDUE-S1", "DEMO-D3-OVERDUE-S3"}


def test_unknown_typed_value_returns_none(container):
    assert ui._resolve_typed_customer(container, "NO-SUCH-CUSTOMER") is None
    assert ui._resolve_typed_customer(container, "") is None
