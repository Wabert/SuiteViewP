"""
Excel template → workbook conversion helpers.

When a file is copied into a policy subfolder, Excel *template* files
(``.xltx`` / ``.xltm`` / ``.xlt``) should be materialized as ordinary
workbooks so the user gets an editable, savable copy rather than a template
that spawns "Book1"-style untitled documents.

Extension mapping:
    .xltx  →  .xlsx   (regular workbook)
    .xltm  →  .xlsm   (macro-enabled workbook)
    .xlt   →  .xls    (legacy workbook)

For the modern (zip-based) OOXML formats the only structural difference
between a template and a workbook is the content type declared in
``[Content_Types].xml``, so conversion is a lossless content-type swap that
preserves everything, including VBA macros for ``.xltm``. Legacy ``.xlt``
files are copied byte-for-byte (Excel opens them as workbooks once renamed).
"""

import os
import shutil
import zipfile

# Source template extension → destination workbook extension.
_TEMPLATE_EXT_MAP = {
    ".xltx": ".xlsx",
    ".xltm": ".xlsm",
    ".xlt": ".xls",
}

# Template main content type → workbook main content type (OOXML formats).
_CONTENT_TYPE_SWAPS = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    "application/vnd.ms-excel.template.macroEnabled.main+xml":
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
}


def is_excel_template(path: str) -> bool:
    """Return True if *path* is an Excel template (.xltx / .xltm / .xlt)."""
    return os.path.splitext(path)[1].lower() in _TEMPLATE_EXT_MAP


def workbook_filename(filename: str) -> str:
    """Return *filename* with any Excel-template extension swapped to its
    regular-workbook equivalent. Non-template names are returned unchanged.
    """
    base, ext = os.path.splitext(filename)
    new_ext = _TEMPLATE_EXT_MAP.get(ext.lower())
    return base + new_ext if new_ext else filename


def _convert_ooxml_template(source_path: str, dest_path: str) -> None:
    """Copy a zip-based template to *dest_path*, swapping the main content
    type so Excel treats it as a workbook rather than a template.
    """
    with zipfile.ZipFile(source_path, "r") as zin:
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    text = data.decode("utf-8")
                    for old, new in _CONTENT_TYPE_SWAPS.items():
                        text = text.replace(old, new)
                    data = text.encode("utf-8")
                zout.writestr(item, data)


def copy_as_workbook(source_path: str, dest_path: str) -> None:
    """Copy *source_path* to *dest_path*.

    If the source is an Excel template, it is converted to a regular
    workbook at *dest_path* (whose extension should already reflect the
    target format, e.g. via :func:`workbook_filename`). Otherwise the file
    is copied verbatim with metadata preserved.
    """
    ext = os.path.splitext(source_path)[1].lower()
    if ext in (".xltx", ".xltm"):
        _convert_ooxml_template(source_path, dest_path)
    else:
        # Legacy .xlt and all non-template files: straight copy.
        shutil.copy2(source_path, dest_path)
