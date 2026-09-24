from redactor import process_file


def test_generated_medical_pdf_fixture_exists(generated_medical_pdf):
    assert generated_medical_pdf.exists()
    assert generated_medical_pdf.stat().st_size > 0


def test_core_redaction_preserves_non_birth_exam_date(tmp_path):
    from conftest import EmptyNerPipeline, FakeConverter

    markdown = """
Beteg neve: Teszt Elek
TAJ szam: 123 456 789
Szuletesi datum: 1980. 01. 02.
Vizsgalat datuma: 2026. 07. 05.
Email: teszt.elek@example.com
Telefon: +36 30 123 4567

| Vizsgalat | Eredmeny | Egyseg | Referencia |
| --- | --- | --- | --- |
| GGT | 45 | U/l | 0-55 |
"""

    pdf_path = tmp_path / "Teszt Elek lelet.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    redacted = process_file(
        str(pdf_path),
        EmptyNerPipeline(),
        FakeConverter(markdown),
    )

    assert "Teszt Elek" not in redacted
    assert "123 456 789" not in redacted
    assert "1980. 01. 02." not in redacted
    assert "teszt.elek@example.com" not in redacted
    assert "+36 30 123 4567" not in redacted
    assert "[REDACTED_NAME]" in redacted
    assert "[REDACTED_DOB]" in redacted
    assert "Vizsgalat datuma: 2026. 07. 05." in redacted
    assert "| GGT | 45 | U/l | 0-55 |" in redacted


def test_birth_date_preceded_by_place_on_own_line_is_redacted(tmp_path):
    from conftest import EmptyNerPipeline, FakeConverter

    # Common ambulance-sheet layout: the label and the value end up on
    # separate markdown lines, and the value line starts with the birth place.
    markdown = """
Szül. hely, idő:

Szeged 1985.03.14. (40 éves)

Ellátás kezdete: 2025.11.20. 10:15
"""

    pdf_path = tmp_path / "lelet.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    redacted = process_file(
        str(pdf_path),
        EmptyNerPipeline(),
        FakeConverter(markdown),
    )

    assert "1985.03.14" not in redacted
    assert "[REDACTED_DOB]" in redacted
    assert "Ellátás kezdete: 2025.11.20. 10:15" in redacted


def test_redact_filename_keeps_document_type_suffix():
    from redactor import redact_filename

    assert (
        redact_filename("2025-01-15 - Kiss-Kovács Péter - Lelet.pdf")
        == "2025-01-15 - [REDACTED_NAME] - Lelet"
    )
    assert (
        redact_filename("2025-01-15 - Nagy-Szabó Anna - Vizsgálat.pdf")
        == "2025-01-15 - [REDACTED_NAME] - Vizsgálat"
    )


def _regex_redact(markdown: str) -> str:
    from redactor import _find_regex_pii, _merge_spans, _redact

    return _redact(markdown, _merge_spans(_find_regex_pii(markdown)))


def test_parenthesized_landline_and_fax_numbers_are_redacted():
    redacted = _regex_redact(
        "Tel.: (06) 31-234-567, Fax: (45) 62-345-678\n"
    )

    assert "(06) 31-234-567" not in redacted
    assert "(45) 62-345-678" not in redacted
    assert redacted.count("[REDACTED_PHONE]") == 2


def test_slash_landlines_and_extensions_are_redacted():
    redacted = _regex_redact(
        "Elérhetőség (telefon) MSZ:47/234 - 567, FGY:46/345 - 678/123\n"
    )

    assert "47/234 - 567" not in redacted
    assert "46/345 - 678/123" not in redacted
    assert redacted.count("[REDACTED_PHONE]") == 2


def test_dr_prefixed_names_are_redacted_without_ner():
    redacted = _regex_redact(
        "## Dr.Bodnár\n\nBeutaló: dr.Balogh Ede\n\nKonzulens orvos: Dr. Fehér Éva\n"
        "Mellkas felvétel\n\nDr. Kis\n"
    )
    for leaked in ("Bodnár", "Balogh", "Fehér", "Kis"):
        assert leaked not in redacted
    assert "[REDACTED_NAME]" in redacted


def test_dr_suffixed_name_is_redacted():
    redacted = _regex_redact("Validáló: Szalai Júlia Dr.\n")
    assert "Szalai" not in redacted
    assert "[REDACTED_NAME]" in redacted


def test_dr_name_does_not_swallow_next_sentence_across_newlines():
    redacted = _regex_redact("Dr.Bodnár\n\nCsontszerkezeti eltérés nem látszik.\n")
    assert "Bodnár" not in redacted
    assert "Csontszerkezeti eltérés nem látszik." in redacted


def test_doctor_stamp_ids_are_redacted():
    redacted = _regex_redact(
        "Beküldő orvos: Kovács Éva (EESZT: O41234)\n"
        "## Nagyné Kis Mária (azonosító: 200001)\n"
        "Szabó Pál (30001) Szemész szakorvos\n"
        "Kertész Anna (A01234)\n"
        "Kis Piroska  O54321 adjunktus\n"
    )
    for leaked in ("O41234", "200001", "30001", "A01234", "O54321"):
        assert leaked not in redacted
    assert "[REDACTED_DOCTOR_ID]" in redacted


def test_company_ids_are_redacted():
    redacted = _regex_redact(
        "Székhely: 1051 Budapest. Cégjegyzékszám: 01-09-100001\nAdószám: 10000001-2-41\n"
    )
    assert "01-09-100001" not in redacted
    assert "10000001-2-41" not in redacted
    assert redacted.count("[REDACTED_COMPANY_ID]") == 2


def test_record_ids_are_redacted():
    redacted = _regex_redact(
        "Naplószám:\n\n00001234\n\nNaplósorszám: 010001234 diagnózis: J0690\n"
        "Ellátás: (1) 2026.01.15 10:00:00 150199999-2026-00012345\n"
    )
    for leaked in ("00001234", "010001234", "150199999-2026-00012345"):
        assert leaked not in redacted
    assert "[REDACTED_RECORD_ID]" in redacted


def test_all_caps_name_after_label_is_redacted():
    redacted = _regex_redact("NÉV: MINTA-HORVATH ARON\nTAJ: 123 456 789\n")
    assert "MINTA" not in redacted
    assert "ARON" not in redacted


def test_all_caps_name_before_reszere_is_redacted():
    redacted = _regex_redact(
        "ÉLES LATAST BIZTOSITO SZEMOVEG MINTA-HORVATH ARON RÉSZERE MUNKASZAM:50000001\n"
        "Készült Nagy-Kovács Péter részére.\n"
    )
    assert "MINTA" not in redacted
    assert "ARON" not in redacted
    assert "Nagy-Kovács" not in redacted
    assert "50000001" not in redacted  # munkaszám is a RECORD_ID
    assert "SZEMOVEG" in redacted  # the item itself survives


def test_name_keyword_inside_word_does_not_fire():
    # "Megnevezés" contains "nev"; under (?i) the old pattern ate the header.
    redacted = _regex_redact("Megnevezés Eredmény Egység Referencia tartomány\n")
    assert redacted == "Megnevezés Eredmény Egység Referencia tartomány\n"


def test_record_labels_sorszam_and_certificate():
    redacted = _regex_redact(
        "Sorszám _: 5 5 0 0\nSorszám: 2019000001\n"
        "Ambulans lap szám: 10001/2021\n"
        "Védettségi igazolvány szám: V10000001\n"
    )
    for leaked in ("5 5 0 0", "2019000001", "10001/2021", "V10000001"):
        assert leaked not in redacted


def test_small_table_row_sorszam_survives():
    redacted = _regex_redact("| Sorszám: | 1 |\n| Sorszám: | 27 |\n")
    assert "| 1 |" in redacted
    assert "| 27 |" in redacted


def test_stamp_id_adjacent_to_name_is_redacted():
    from redactor import _find_ids_near_names, _find_regex_pii, _merge_spans, _redact

    text = (
        "Orvos    : (41234) Fehér Éva Dr.\n"
        "O76543 Dr. Bodnár Eduárd\n"
        "51234\n\ndr. Gál Katalin\n"
        + "lab eredmények referencia tartománya következik alább " * 3
        + "\nReferencia tartomány 12345 nincs név a közelben\n"
    )
    spans = _merge_spans(_find_regex_pii(text))
    spans = _merge_spans(spans + _find_ids_near_names(text, spans))
    redacted = _redact(text, spans)
    for leaked in ("41234", "O76543", "51234"):
        assert leaked not in redacted
    assert "12345" in redacted  # no name nearby: survives


def test_manual_redact_folds_accents_and_case(tmp_path):
    from redactor import manual_redact_folder

    md = tmp_path / "out.md"
    md.write_text(
        "SZEMOVEG MINTA-HORVATH ARON RÉSZERE\nMinta-Horváth Áron aláírása\n",
        encoding="utf-8",
    )
    replacements, files = manual_redact_folder(str(tmp_path), "Minta-Horváth Áron")
    text = (tmp_path / "out.md").read_text(encoding="utf-8")
    assert files == 1
    assert "MINTA" not in text
    assert "Áron" not in text


def test_redact_filename_handles_all_caps():
    from redactor import redact_filename

    assert "KOVACS" not in redact_filename("2025-01-15 - KOVACS-KIS PETER - Lelet.pdf")


def test_title_suffixed_and_alulirott_names_are_redacted():
    redacted = _regex_redact(
        # OCR-garbled signature block: NER misses it, the title anchors it
        "Kerekes-Reisz Lea Onolya Optometrista, kontaktológus Műk.nyilv.sz:100001\n"
        "Alulírott Nagyné Kiss Klára igazolom, hogy...\n"
    )
    assert "Kerekes" not in redacted
    assert "Onolya" not in redacted
    assert "Nagyné Kiss Klára" not in redacted


def test_lone_capitalized_word_before_title_survives():
    redacted = _regex_redact("Konzulens orvos aláírása\nVizsgáló orvos\n")
    assert redacted == "Konzulens orvos aláírása\nVizsgáló orvos\n"


def test_low_confidence_ner_spans_are_dropped():
    from redactor import _find_ner_pii

    class FakePipeline:
        def count_tokens(self, text):
            return len(text.split())

        def __call__(self, text):
            return [
                {"entity_group": "PER", "start": 0, "end": 4, "word": text[0:4], "score": 0.95},
                {"entity_group": "PER", "start": 5, "end": 9, "word": text[5:9], "score": 0.45},
            ]

    spans = _find_ner_pii("Alma Kört question", FakePipeline())
    assert any(s.score and s.score > 0.9 for s in spans)
    assert not any(s.score and s.score < 0.7 for s in spans)


def test_isolated_midword_ner_span_is_dropped_but_supported_kept():
    from redactor import PiiSpan, _drop_isolated_midword_spans

    text = "Gyógyszer: Aspirin, Mobiflex es Kéri-Molnár Ádám"
    lone_mid = PiiSpan(20, 22, "NAME", "Mo", score=0.71)  # eats into Mobiflex
    frag_a = PiiSpan(32, 35, "NAME", "Kér", score=0.99)
    frag_b = PiiSpan(35, 48, "NAME", "i-Molnár Ádám", score=0.99)
    kept = _drop_isolated_midword_spans(text, [lone_mid, frag_a, frag_b], [])
    assert lone_mid not in kept
    assert frag_a in kept and frag_b in kept


def test_partial_word_ner_fragments_do_not_redact_medical_terms():
    from redactor import PiiSpan, _drop_isolated_midword_spans

    text = "Parathormon és Mko teszt"
    spans = [
        PiiSpan(0, 3, "LOCATION", "Par", score=0.93),
        PiiSpan(3, 6, "LOCATION", "ath", score=0.97),
        PiiSpan(15, 16, "NAME", "M", score=0.93),
    ]

    assert _drop_isolated_midword_spans(text, spans, []) == []


def test_address_without_space_before_house_number_is_redacted():
    redacted = _regex_redact("Lakcím: Budapest, Minta út18")

    assert "Minta" not in redacted
    assert "út18" not in redacted
    assert "[REDACTED_ADDRESS]" in redacted


def test_inflected_location_is_redacted_through_hungarian_suffix():
    from redactor import PiiSpan, _drop_isolated_midword_spans, _redact

    text = "Nyíregyházára küldve"
    spans = [
        PiiSpan(0, 8, "LOCATION", "Nyíregy", score=0.98),
        PiiSpan(8, 11, "LOCATION", "ház", score=0.94),
    ]

    kept = _drop_isolated_midword_spans(text, spans, [])

    assert _redact(text, kept) == "[REDACTED_LOCATION] küldve"


def test_fragmented_multiword_name_expands_to_word_boundary():
    from redactor import PiiSpan, _drop_isolated_midword_spans, _redact

    text = "Rácz Fanni lelete"
    spans = [PiiSpan(0, 8, "NAME", "Rácz Fan", score=0.73)]

    kept = _drop_isolated_midword_spans(text, spans, [])

    assert _redact(text, kept) == "[REDACTED_NAME] lelete"


def test_repeated_full_width_table_note_is_kept_once():
    from redactor import _collapse_repeated_table_row_cells

    markdown = (
        "| Vizsgálat | Eredmény | Státusz |\n"
        "|---|---|---|\n"
        "| Nyíregyházára küldve. | Nyíregyházára küldve. | Nyíregyházára küldve. |\n"
        "| Nátrium | 139 mmol/L | VALIDÁLT |\n"
    )

    collapsed = _collapse_repeated_table_row_cells(markdown)

    assert collapsed.count("Nyíregyházára küldve.") == 1
    assert "|---|---|---|" in collapsed
    assert "| Nátrium | 139 mmol/L | VALIDÁLT |" in collapsed


def test_institution_codes_are_not_taj_redacted():
    # 9-digit NNGYK/NEAK institution codes can pass the TAJ checksum; they
    # identify the lab, not the patient, and must survive.
    redacted = _regex_redact("Laboratórium (NNGYK: 010099904, NEAK: 310199900)\n")
    assert "010099904" in redacted
    assert "310199900" in redacted
    assert "[REDACTED_TAJ]" not in redacted


def test_ner_chunking_runs_shifted_second_pass():
    from redactor import _find_ner_pii

    class RecordingPipeline:
        def __init__(self):
            self.calls = 0

        def count_tokens(self, text: str) -> int:
            return len(text.split())

        def __call__(self, text: str) -> list[dict]:
            self.calls += 1
            return []

    pipeline = RecordingPipeline()
    _find_ner_pii("word " * 400, pipeline)  # 2000 chars
    # stride 600: pass 1 covers offsets 0/600/1200/1800 (4 chunks),
    # pass 2 covers 300/900/1500 (3 chunks)
    assert pipeline.calls == 7


def test_process_pdfs_uniquifies_colliding_output_names(tmp_path, monkeypatch):
    import redactor
    from conftest import EmptyNerPipeline, FakeConverter

    monkeypatch.setattr(
        redactor, "build_docling_converter", lambda: FakeConverter("Beteg neve: Teszt Elek")
    )
    monkeypatch.setattr(redactor, "load_ner_model", lambda: EmptyNerPipeline())

    # Same date, no doc-type suffix: both stems redact to the same base name.
    for stem in ("2025-01-15 - Kiss-Kovács Péter", "2025-01-15 - Nagy-Szabó Anna"):
        (tmp_path / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n")

    out_dir = tmp_path / "out"
    redactor.process_pdfs(
        [str(p) for p in sorted(tmp_path.glob("*.pdf"))],
        str(out_dir),
    )

    assert {p.name for p in out_dir.glob("*.md")} == {
        "2025-01-15 - [REDACTED_NAME].md",
        "2025-01-15 - [REDACTED_NAME] (2).md",
    }
