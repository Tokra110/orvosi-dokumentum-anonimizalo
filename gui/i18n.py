"""Tiny in-app translation registry (HU default, EN secondary).

No Qt imports: strings only. Widgets read `t(key)` at build time and again in
`MainWindow._retranslate()` after the language toggle flips `_lang`. The queue
table model and models dialog read `t()` lazily, so they pick up the current
language whenever they repaint or reopen.
"""

LANGUAGES = ("hu", "en")
_DEFAULT = "hu"

_lang = _DEFAULT


def set_language(lang: str) -> None:
    global _lang
    if lang in LANGUAGES:
        _lang = lang


def get_language() -> str:
    return _lang


def other_language() -> str:
    return "en" if _lang == "hu" else "hu"


def t(key: str, **kwargs) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_lang, entry.get("en", key))
    return text.format(**kwargs) if kwargs else text


_STRINGS: dict[str, dict[str, str]] = {
    # --- header / window ---
    "app_title": {
        "hu": "Orvosi dokumentum anonimizáló",
        "en": "Medical document anonymizer",
    },
    "lang_tooltip": {
        "hu": "Az alkalmazás nyelvének váltása",
        "en": "Switch the application language",
    },
    "chip_ready": {"hu": "Modellek készen", "en": "Models ready"},
    "chip_missing": {"hu": "Modellek letöltése", "en": "Download models"},
    "chip_tooltip": {
        "hu": (
            "Az anonimizáláshoz két helyi MI-modell szükséges: egy magyar név- és "
            "helyfelismerő (HuBERT NER) és egy táblázatolvasó (TableFormer). Ez a "
            "jelvény mutatja, hogy mindkettő megvan-e; kattints rá az állapot "
            "megtekintéséhez vagy a hiányzók letöltéséhez. Az indítás addig tiltott, "
            "amíg mindkettő készen nem áll."
        ),
        "en": (
            "Redaction needs two local AI models: a Hungarian name/place detector "
            "(HuBERT NER) and a table-reader (TableFormer). This chip shows whether "
            "both are present; click it to see status or download what's missing. "
            "Start is blocked until both are ready."
        ),
    },
    "banner_missing": {
        "hu": (
            "Hiányoznak a modellfájlok — az anonimizálás nem futtatható. "
            "A részletekért nyisd meg a modellállapotot."
        ),
        "en": (
            "Model files are missing — redaction can't run. "
            "Open the model status for details."
        ),
    },
    # --- queue card ---
    "queue_title": {"hu": "Feldolgozási sor", "en": "Processing queue"},
    "count_empty": {"hu": "A sor üres", "en": "Queue empty"},
    "count_files": {"hu": "{n} fájl", "en": "{n} file(s)"},
    "add_files": {"hu": "PDF fájlok hozzáadása", "en": "Add PDF files"},
    "add_folder": {"hu": "Mappa hozzáadása", "en": "Add folder"},
    "add_folder_tooltip": {
        "hu": (
            "A mappában közvetlenül található összes PDF hozzáadása a sorhoz. "
            "Az almappákat nem vizsgálja. Egy mappát az ablakra is ráhúzhatsz."
        ),
        "en": (
            "Add every PDF sitting directly in a folder to the queue. "
            "Sub-folders are not scanned. You can also drag a folder anywhere onto "
            "the window."
        ),
    },
    "clear": {"hu": "Törlés", "en": "Clear"},
    "clear_tooltip": {
        "hu": (
            "A sor kiürítése. Csak akkor érhető el, ha éppen nem folyik feldolgozás; "
            "a lemezre már exportált fájlokat nem érinti."
        ),
        "en": (
            "Empty the queue. Only available while nothing is being processed; "
            "already-exported files on disk are not touched."
        ),
    },
    "drop_hint": {
        "hu": "vagy húzz PDF fájlokat / mappákat bárhová az ablakban",
        "en": "or drop PDF files / folders anywhere in this window",
    },
    "remove_from_queue": {"hu": "Eltávolítás a sorból", "en": "Remove from queue"},
    "table_tooltip": {
        "hu": (
            "Minden sor egy PDF. Oszlopok:\n"
            "• Fájl — a PDF neve\n"
            "• Állapot — sorban / átalakítás / felismerés / kész / hiba\n"
            "• Nevek, TAJ, Dátumok, Cím — az egyes PII-típusokból hány lett anonimizálva\n"
            "• Összes — az adott fájl összes anonimizálása.\n"
            "A nulla nevet tartalmazó sort borostyánszín jelöli — érdemes kézzel ellenőrizni."
        ),
        "en": (
            "Each row is one PDF. Columns:\n"
            "• File — the PDF name\n"
            "• Status — queued / converting / detecting / done / error\n"
            "• Names, TAJ, Dates, Addr. — how many of each PII type were redacted\n"
            "• Total — all redactions in that file.\n"
            "A row with zero names is flagged amber — worth a manual check."
        ),
    },
    # --- footer / run control ---
    "start": {"hu": "Indítás", "en": "Start"},
    "start_tooltip": {
        "hu": (
            "A sorban lévő összes PDF anonimizálása. Minden fájl Markdownná alakul, "
            "majd a nevek, TAJ-számok, címek, telefonszámok, e-mail-címek és születési "
            "dátumok helyére [REDACTED_NAME]-szerű helyőrzők kerülnek. A kimenet oda "
            "kerül, amit a Kimenet gomb mutat. A vizsgálati dátumok szándékosan "
            "megmaradnak — csak a születési dátumokat távolítja el."
        ),
        "en": (
            "Redact every queued PDF. Each file is converted to Markdown, then names, "
            "TAJ numbers, addresses, phones, emails and birth dates are replaced with "
            "placeholders like [REDACTED_NAME]. Output goes where the Output button "
            "says. Examination dates are kept on purpose — only birth dates are removed."
        ),
    },
    "stop": {"hu": "Leállítás", "en": "Stop"},
    "stop_tooltip": {
        "hu": (
            "Leállítás az éppen feldolgozott fájl befejezése után. A már kész fájlok "
            "kimenete megmarad; a többi a sorban marad."
        ),
        "en": (
            "Stop after the file currently being processed finishes. Files already "
            "done keep their output; the rest stay queued."
        ),
    },
    "output_beside_menu": {"hu": "Az eredetiek mellé", "en": "Beside originals"},
    "output_choose_menu": {"hu": "Mappa választása…", "en": "Choose folder…"},
    "output_beside_btn": {
        "hu": "Kimenet: az eredetiek mellé",
        "en": "Output: beside originals",
    },
    "output_folder_btn": {"hu": "Kimenet: {name}", "en": "Output: {name}"},
    "output_tooltip": {
        "hu": (
            "Hová íródnak az anonimizált .md fájlok:\n"
            "• Az eredetiek mellé — minden .md a forrás PDF mellé kerül\n"
            "• Mappa választása… — az összes kimenet egy általad választott mappába kerül.\n"
            "A választás megőrződik a munkamenetek között."
        ),
        "en": (
            "Where redacted .md files are written:\n"
            "• Beside originals — each .md is saved next to its source PDF\n"
            "• Choose folder… — collect all output in one folder you pick.\n"
            "Your choice is remembered between sessions."
        ),
    },
    "activity_converting": {"hu": "{name} átalakítása…", "en": "Converting {name}…"},
    "activity_redacting": {
        "hu": "PII keresése ebben: {name}…",
        "en": "Detecting PII in {name}…",
    },
    "activity_stopping": {
        "hu": "Leállítás az aktuális fájl után…",
        "en": "Stopping after the current file…",
    },
    # --- manual redact card ---
    "manual_title": {"hu": "Kézi anonimizálás", "en": "Manual redact"},
    "manual_hint": {
        "hu": "érték cseréje az exportált .md fájlokban",
        "en": "replace a value across exported .md files",
    },
    "manual_section_tip": {
        "hu": (
            "Utólagos tisztítás mindarra, amit az automatikus anonimizálás kihagyott. "
            "Futtasd a feldolgozás után: írj be egy pontos értéket (pl. egy beteg "
            "nevét), és a választott mappa minden .md fájljában lecserélődik — a "
            "felcserélt, kötőjeles és egybeírt változatokkal együtt."
        ),
        "en": (
            "A cleanup pass for anything the automatic redaction missed. Run it after "
            "processing: type an exact value (e.g. a patient's name), and every .md "
            "file in the chosen folder has it replaced — including reordered, "
            "hyphenated and concatenated variants."
        ),
    },
    "manual_value_label": {"hu": "Érték", "en": "Value"},
    "manual_value_tip": {
        "hu": (
            "A pontosan eltávolítandó szöveg, pl. „Kiss Pál” vagy egy telefonszám. "
            "A gyakori változatokat (szórend, kötőjelek, szóközök) automatikusan kezeli."
        ),
        "en": (
            "The exact text to remove, e.g. \"Kiss Pál\" or a phone number. Common "
            "variants (word order, hyphens, spacing) are handled automatically."
        ),
    },
    "manual_type_label": {"hu": "Típus", "en": "Type"},
    "manual_type_tip": {
        "hu": (
            "Melyik helyőrzőre cserélődik az érték, hogy az anonimizált szöveg címkézett "
            "maradjon — az értékből [REDACTED_<típus>] lesz:\n"
            "• NAME — személy neve\n"
            "• TAJ — magyar TAJ-szám\n"
            "• DOB — születési dátum\n"
            "• ADDRESS — utca / postai cím\n"
            "• PHONE — telefonszám\n"
            "• EMAIL — e-mail-cím\n"
            "• LOCATION — helynév\n"
            "• ORG — szervezet / intézmény\n"
            "• CUSTOM — általános [REDACTED_CUSTOM] címke"
        ),
        "en": (
            "Which placeholder the value is replaced with, so redacted text stays "
            "labelled — the value becomes [REDACTED_<type>]:\n"
            "• NAME — a person's name\n"
            "• TAJ — Hungarian social-security number\n"
            "• DOB — date of birth\n"
            "• ADDRESS — street / postal address\n"
            "• PHONE — phone number\n"
            "• EMAIL — email address\n"
            "• LOCATION — place name\n"
            "• ORG — organisation / institution\n"
            "• CUSTOM — generic [REDACTED_CUSTOM] label"
        ),
    },
    "manual_folder_label": {"hu": "Mappa", "en": "Folder"},
    "manual_folder_tip": {
        "hu": (
            "Az utólag tisztítandó, már exportált .md fájlokat tartalmazó mappa. "
            "Alapból a kimeneti mappa; a csere a benne lévő összes .md fájlon lefut."
        ),
        "en": (
            "The folder holding the already-exported .md files to clean up. Defaults "
            "to your output folder; the replacement runs across every .md inside it."
        ),
    },
    "manual_folder_placeholder": {
        "hu": "az exportált .md fájlokat tartalmazó mappa",
        "en": "folder with exported .md files",
    },
    "browse": {"hu": "Tallózás…", "en": "Browse…"},
    "manual_run": {"hu": "Anonimizálás minden fájlban", "en": "Redact from all files"},
    "manual_run_tooltip": {
        "hu": (
            "A fenti érték cseréje most a mappa összes .md fájljában. "
            "A cserék száma a naplóba kerül."
        ),
        "en": (
            "Replace the value above across every .md file in the folder now. "
            "The number of replacements is written to the log."
        ),
    },
    # --- log section ---
    "log_title": {"hu": "Napló", "en": "Log"},
    "log_hint": {
        "hu": "tisztított, biztonságosan megosztható",
        "en": "sanitized, safe to share",
    },
    # --- file dialogs ---
    "dlg_add_files": {"hu": "PDF fájlok hozzáadása", "en": "Add PDF files"},
    "dlg_pdf_filter": {"hu": "PDF fájlok (*.pdf)", "en": "PDF files (*.pdf)"},
    "dlg_add_folder": {"hu": "PDF-eket tartalmazó mappa", "en": "Add a folder of PDFs"},
    "dlg_output_folder": {"hu": "Kimeneti mappa választása", "en": "Choose output folder"},
    "dlg_manual_folder": {
        "hu": "Exportált .md fájlokat tartalmazó mappa",
        "en": "Folder with exported .md files",
    },
    # --- log / status messages ---
    "log_no_new": {
        "hu": "Nincs új PDF fájl a hozzáadáshoz.",
        "en": "No new PDF files to add.",
    },
    "log_models_missing": {
        "hu": "Hiányoznak a modellfájlok — nyisd meg a modellállapot jelvényt.",
        "en": "Model files are missing — open the model status chip.",
    },
    "log_nothing": {
        "hu": "Nincs feldolgozandó — először adj hozzá PDF fájlokat.",
        "en": "Nothing to process — add PDF files first.",
    },
    "log_enter_value": {
        "hu": "Adj meg egy anonimizálandó értéket.",
        "en": "Enter a value to redact.",
    },
    "log_pick_folder": {
        "hu": "Válassz egy exportált .md fájlokat tartalmazó mappát.",
        "en": "Pick a folder containing exported .md files.",
    },
    "log_manual_done": {
        "hu": "Kézi anonimizálás: {count} előfordulás cserélve {files} fájlban ehhez: [{label}]",
        "en": "Manual redact: replaced {count} occurrences across {files} files for [{label}]",
    },
    # --- queue table model ---
    "col_file": {"hu": "Fájl", "en": "File"},
    "col_status": {"hu": "Állapot", "en": "Status"},
    "col_names": {"hu": "Nevek", "en": "Names"},
    "col_taj": {"hu": "TAJ", "en": "TAJ"},
    "col_dates": {"hu": "Dátumok", "en": "Dates"},
    "col_addr": {"hu": "Cím", "en": "Addr."},
    "col_total": {"hu": "Összes", "en": "Total"},
    "status_queued": {"hu": "Sorban", "en": "Queued"},
    "status_converting": {"hu": "Átalakítás…", "en": "Converting…"},
    "status_redacting": {"hu": "Anonimizálás…", "en": "Redacting…"},
    "status_done": {"hu": "Kész", "en": "Done"},
    "status_failed": {"hu": "Hiba", "en": "Failed"},
    "zero_names": {"hu": "0 név", "en": "0 names"},
    # --- models dialog ---
    "models_title": {"hu": "Modellfájlok", "en": "Model files"},
    "installed": {"hu": "Telepítve", "en": "Installed"},
    "download": {"hu": "Letöltés", "en": "Download"},
    "cancel": {"hu": "Mégse", "en": "Cancel"},
    "close": {"hu": "Bezárás", "en": "Close"},
    "model_folder": {"hu": "Modellmappa: {dir}", "en": "Model folder: {dir}"},
    "dl_not_configured_title": {
        "hu": "A letöltési forrás nincs beállítva",
        "en": "Download source not configured",
    },
    "dl_not_configured_body": {
        "hu": (
            "A(z) „{name}” modellhez még nincs beállítva letöltési forrás.\n\n"
            "Másold az exportált mappát ide:\n{dir}\n\n"
            "A tárhelyről való letöltés egy későbbi verzióban lesz beállítva "
            "(models_manifest.json → base_url)."
        ),
        "en": (
            "No download source is set for '{name}' yet.\n\n"
            "Copy the exported folder into:\n{dir}\n\n"
            "A hosted download will be configured in a later version "
            "(models_manifest.json → base_url)."
        ),
    },
    "dl_failed_title": {"hu": "A letöltés sikertelen", "en": "Download failed"},
}
