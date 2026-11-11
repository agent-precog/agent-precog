"""Build digest.md: a compact, complete plain-text snapshot of the review for the site agent.

The agent answers only from this file, so it must contain everything a visitor can see:
the project overview, RQs, pillars (with scope and search string), the gap matrix, the
PRISMA-S method, the Foundations text, the changelog and every paper with its scores.
Called from build.py after the pages are rendered; reads the rendered HTML so the prose
is exactly what visitors see.
"""
import re
from html.parser import HTMLParser
from pathlib import Path


class _Text(HTMLParser):
    BLOCK = {"p", "h1", "h2", "h3", "h4", "li", "tr", "div", "section", "figcaption", "br", "table"}
    SKIP = {"script", "style", "nav", "header", "footer", "svg", "select", "option", "button", "summary"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip, self._cell = [], 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag in ("td", "th"):
            self._cell = True
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3"):
            self.parts.append("\n" + "#" * (int(tag[1]) + 2) + " ")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag in ("td", "th"):
            self.parts.append(" | ")
            self._cell = False

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self):
        t = "".join(self.parts)
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r" ?\n ?", "\n", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()


def page_text(path: Path) -> str:
    p = _Text()
    p.feed(path.read_text(encoding="utf-8"))
    return p.text()


def build_digest(out: Path, *, site_name, site_url, version, papers, pillars, rqs, gap_columns, matrix, counts, changelog):
    L = []
    L.append(f"# {site_name} - review digest (v{version['version']}, released {version['released']}, protocol v{version['protocol']})")
    L.append(f"Site: {site_url}. Next scheduled search run: {version['next_search']}. Papers included: {len(papers)}.")
    L.append("This digest is regenerated at every release from the same CSV files as the site. Deep links: /rqs/, /pillars/, /gap/, /papers/ (filters ?rq=rqN and ?method=TAG), /foundations/, /prisma-s/, /changelog/, /pillars/<slug>/.")

    L.append("\n## Home page (project overview, quantities, unsolved problems)")
    L.append(page_text(out / "index.html"))

    L.append("\n## Research questions")
    L.append(page_text(out / "rqs" / "index.html"))

    L.append("\n## Pillars")
    for pl in pillars:
        L.append(f"\n### Pillar {pl['n']}: {pl['name']} (slug: {pl['slug']}, {pl['count']} papers)")
        L.append(f"Scope: {pl['scope']}")
        L.append(f"Search string: {pl['query']}")

    L.append("\n## Gap matrix (rows = pillars, columns = requirements; cell = number of included papers tagged)")
    L.append("Columns: " + "; ".join(label for _, label in gap_columns))
    for row in matrix:
        cells = ", ".join(f"{c['label']}={c['count']}" for c in row["cells"])
        L.append(f"- Pillar {row['pillar']['n']} ({row['pillar']['short']}): {cells}")

    L.append("\n## PRISMA 2020 counts")
    if counts.get("has_runs"):
        L.append(f"Identified {counts['identified_db']} from {counts['databases']} databases; after dedup {counts['screened']}; full text {counts['full_text']}; included {counts['included']}.")
    else:
        L.append(f"No database search runs yet; the review currently holds the hand-curated seed list of {counts['included']} papers. First automated run: {version['next_search']}.")

    L.append("\n## Method (PRISMA-S page)")
    L.append(page_text(out / "prisma-s" / "index.html"))

    L.append("\n## Foundations (formal model)")
    L.append(page_text(out / "foundations" / "index.html"))

    L.append("\n## Changelog")
    for c in changelog:
        L.append(f"- {c['date']} v{c['version']}: {c['change']}")

    L.append("\n## All included papers")
    L.append("Format: id | title | authors | year | venue | pillars | relevance per RQ (0-5) | gap cells | baseline | methods | url | contribution")
    for p in papers:
        scores = ", ".join(f"{k.upper()}={p[k]}" for k, _, _ in rqs)
        L.append(
            f"- {p['id']} | {p['title']} | {p['authors']} | {p['year']} | {p['venue']} | pillars {','.join(map(str, p['pillar_list']))} | "
            f"{scores} | gaps: {'; '.join(p['gap_list']) or 'none'} | baseline: {'yes' if p['baseline'] else 'no'} | "
            f"methods: {'; '.join(p['methods_list'])} | {p['url']} | {p['contribution']}"
        )

    text = "\n".join(L) + "\n"
    (out / "digest.md").write_text(text, encoding="utf-8")
    return len(text)
