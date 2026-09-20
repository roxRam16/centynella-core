from datetime import UTC

from src.models import BaseDocument, utc_now


def test_utc_now_tiene_zona_horaria():
    assert utc_now().tzinfo is UTC


def test_base_document_asigna_auditoria_y_acepta_alias_id():
    doc = BaseDocument.model_validate({"_id": "abc123"})

    assert doc.id == "abc123"
    assert doc.created_at.tzinfo is not None
    assert doc.updated_at.tzinfo is not None


def test_base_document_sin_id_es_valido():
    assert BaseDocument().id is None
