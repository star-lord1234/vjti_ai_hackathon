from pathlib import Path

from parser.metadata import GRParser
from parser.normalize import normalize_metadata 

file_path = Path(
    "/Users/biancasawant/vjti/maha_grs 2/maha_grs/fulltext/in.gov.maharashtra.gr.20060927181830001.txt"
)

text = file_path.read_text(
    encoding="utf-8",
    errors="ignore"
)

parser = GRParser(text, filename=file_path.name)

metadata = parser.extract_metadata()
metadata = normalize_metadata(metadata)

print(metadata)