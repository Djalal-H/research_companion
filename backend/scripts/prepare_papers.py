"""Download selected sections from pinned arXiv HTML revisions for local use.

The generated extracts are ignored by Git; source rights remain with the authors.
No PDF ingestion, OCR, or runtime web search is involved.
"""

import hashlib
import json
import re
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

DIRECTORY = Path(__file__).resolve().parents[2] / "data/papers"


def main():
    manifest = json.loads((DIRECTORY / "manifest.json").read_text())
    for spec in manifest["papers"]:
        request = urllib.request.Request(
            spec["url"], headers={"User-Agent": "ResearchCompanion/0.1"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            html = response.read()
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("h1.ltx_title")
        if title is None:
            raise ValueError(f"Missing paper title: {spec['url']}")
        sections = []
        for section_id in spec["sections"]:
            section = soup.find(id=section_id)
            if section is None:
                raise ValueError(f"Missing section {section_id}: {spec['url']}")
            heading = section.find(re.compile("^h[1-6]$"))
            # Keep headings/paragraphs, including nested method subsections. Exclude navigation.
            text = "\n\n".join(
                re.sub(r"\s+", " ", element.get_text(" ", strip=True))
                for element in section.find_all(["h2", "h3", "h4", "p"])
            )
            if not text.strip():
                raise ValueError(f"Empty extraction: {spec['id']} {section_id}")
            sections.append(
                {"id": section_id, "title": heading.get_text(" ", strip=True), "text": text}
            )
        data = {
            "id": spec["id"],
            "title": title.get_text(" ", strip=True),
            "url": spec["url"],
            "sections": sections,
            "html_sha256": hashlib.sha256(html).hexdigest(),
            "extraction": "Selected HTML headings and paragraphs; equations may be incomplete.",
        }
        destination = DIRECTORY / f"{spec['id']}.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(destination)
        print(
            f"Prepared {spec['id']}: {len(sections)} sections, "
            f"{sum(len(s['text']) for s in sections)} characters"
        )


if __name__ == "__main__":
    main()
