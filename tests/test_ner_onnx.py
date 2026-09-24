from medical_redactor_onnx.paths import hubert_ner_dir


def test_onnx_ner_detects_person_location_and_org():
    from medical_redactor_onnx.ner_onnx import OnnxNerPipeline

    nlp = OnnxNerPipeline(hubert_ner_dir(require=True))
    text = "Orbán Viktor Budapesten találkozott a Magyar Tudományos Akadémia képviselőivel."

    entities = nlp(text)

    assert ("PER", "Orbán Viktor") in {
        (entity["entity_group"], entity["word"]) for entity in entities
    }
    assert ("LOC", "Budapesten") in {
        (entity["entity_group"], entity["word"]) for entity in entities
    }
    assert ("ORG", "Magyar Tudományos Akadémia") in {
        (entity["entity_group"], entity["word"]) for entity in entities
    }


def test_redactor_load_ner_model_uses_onnx_runtime():
    from medical_redactor_onnx.ner_onnx import OnnxNerPipeline
    from redactor import load_ner_model

    nlp = load_ner_model()

    assert isinstance(nlp, OnnxNerPipeline)
    assert hasattr(nlp, "tokenizer")
    assert nlp("Kovács János Budapesten lakik.")


def test_onnx_ner_pipeline_matches_find_ner_pii_contract():
    from redactor import _find_ner_pii, load_ner_model

    text = "Teszt Elek Szegeden lakik."
    spans = _find_ner_pii(text, load_ner_model())

    assert ("NAME", "Teszt Elek") in {(span.label, span.text) for span in spans}
    assert ("LOCATION", "Szegeden") in {(span.label, span.text) for span in spans}
