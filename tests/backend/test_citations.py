import pytest

from backend.citation import validate_citations


@pytest.mark.parametrize(("answer", "ids", "valid"), [
    ("No citation.", [], False), ("Claim [S1]. Again [S1].", ["S1"], True),
    ("Claim [S2].", [], False), ("[S0] [Sx]", [], False),
])
def test_citation_validation_is_strict(answer, ids, valid):
    result = validate_citations(answer, {"S1"})
    assert result.cited_source_ids == ids
    assert result.valid is valid
