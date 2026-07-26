from PySide6.QtCore import Qt


def _model(qapp, paths):
    from gui.queue_model import QueueModel

    m = QueueModel()
    m.add_paths(paths)
    return m


def test_add_paths_dedupes_and_filters_non_pdf(qapp, tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.PDF"
    t = tmp_path / "c.txt"
    for f in (a, b, t):
        f.touch()

    m = _model(qapp, [str(a), str(b), str(t), str(a)])
    assert m.rowCount() == 2


def test_event_flow_updates_status_and_counts(qapp, tmp_path):
    from gui import i18n

    i18n.set_language("en")
    a = tmp_path / "a.pdf"
    a.touch()
    m = _model(qapp, [str(a)])

    m.apply_event(str(a), "converting", None, "")
    assert m.data(m.index(0, 1), Qt.DisplayRole) == "Converting…"

    counts = {"NAME": 3, "TAJ": 1, "DATE_OF_BIRTH": 2, "ADDRESS": 1, "LOCATION": 1, "PHONE": 1}
    m.apply_event(str(a), "done", counts, "")
    assert m.data(m.index(0, 1), Qt.DisplayRole) == "Done"
    assert m.data(m.index(0, 2), Qt.DisplayRole) == "3"   # names
    assert m.data(m.index(0, 3), Qt.DisplayRole) == "1"   # taj
    assert m.data(m.index(0, 4), Qt.DisplayRole) == "2"   # dates
    assert m.data(m.index(0, 5), Qt.DisplayRole) == "2"   # addr = ADDRESS + LOCATION
    assert m.data(m.index(0, 6), Qt.DisplayRole) == "9"   # total


def test_zero_names_row_flagged_amber(qapp, tmp_path):
    from gui import i18n

    i18n.set_language("en")
    a = tmp_path / "a.pdf"
    a.touch()
    m = _model(qapp, [str(a)])
    m.apply_event(str(a), "done", {"TAJ": 1}, "")

    assert m.data(m.index(0, 1), Qt.DisplayRole) == "0 names"
    assert m.data(m.index(0, 0), Qt.BackgroundRole) is not None


def test_pending_paths_includes_queued_and_failed_only(qapp, tmp_path):
    a, b, c = (tmp_path / f"{n}.pdf" for n in "abc")
    for f in (a, b, c):
        f.touch()
    m = _model(qapp, [str(a), str(b), str(c)])
    m.apply_event(str(a), "done", {"NAME": 1}, "")
    m.apply_event(str(b), "failed", None, "boom")

    assert m.pending_paths() == [str(b), str(c)]


def test_clear_and_remove_rows(qapp, tmp_path):
    a, b = (tmp_path / f"{n}.pdf" for n in "ab")
    a.touch()
    b.touch()
    m = _model(qapp, [str(a), str(b)])
    m.remove_rows([0])
    assert m.rowCount() == 1
    m.clear()
    assert m.rowCount() == 0
