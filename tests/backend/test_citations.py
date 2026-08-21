import pytest

from backend.citation import validate_citations


@pytest.mark.parametrize(("answer", "ids", "valid"), [
    ("No citation.", [], False), ("Claim [S1]. Again [S1].", ["S1"], True),
    ("Claim [S2].", [], False), ("[S0] [Sx]", [], False),
    ("Compare both sources [S1, S3].", ["S1", "S3"], True),
    ("Mixed known and unknown [S1, S8].", ["S1"], False),
    ("Ranges remain invalid [S1-S3].", [], False),
])
def test_citation_validation_is_strict(answer, ids, valid):
    result = validate_citations(answer, {"S1", "S3"})
    assert result.cited_source_ids == ids
    assert result.valid is valid
