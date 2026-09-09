"""Read the maintained CT actuarial memo; never load a case response."""
import json
from hashlib import sha256
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import fitz

root = Path(__file__).resolve().parents[2]
source = root / "docs" / "ABRQuote" / "Form ABR14-CT Actuarial Memo.pdf"
terms = ("mortality", "survival", "life expectancy", "minimum", "negative", "assessment")
with fitz.open(source) as document:
    excerpts = [
        {"page": index + 1, "text": block[4]}
        for index, page in enumerate(document)
        for block in page.get_text("blocks")
        if any(term in block[4].lower() for term in terms)
    ]
print(json.dumps({"source": str(source.relative_to(root)),
                  "sha256": sha256(source.read_bytes()).hexdigest(),
                  "excerpts": excerpts}, indent=2))
