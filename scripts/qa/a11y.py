"""Automated WCAG 2.1 AA check with axe-core on every page and language,
in light and dark mode, desktop and mobile, with the chat panel open and
all <details> expanded on event pages.

Usage: python scripts/qa/a11y.py --axe path/to/axe.min.js --base http://localhost:8080
Needs Playwright with Chromium (pip install playwright && playwright install chromium)
and axe-core (npm pack axe-core; the file is package/axe.min.js)."""
import argparse
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

PAGES = ["index.html", "metodologia.html", "contestar.html", "eventos/itaquara-emergencia-hidrica.html",
         "eventos/itaquara-publicidade-apostas.html", "eventos/porto-anil-reintegracao-predio.html"]
RULES = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]


async def main(axe_path: str, base: str, chrome: str | None) -> int:
    axe = open(axe_path, encoding="utf-8").read()
    total = checked = 0
    async with async_playwright() as p:
        b = await p.chromium.launch(**({"executable_path": chrome} if chrome else {}))
        for scheme in ("light", "dark"):
            for width in (1280, 375):
                ctx = await b.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
                for lang in ("pt", "es", "en"):
                    for path in PAGES:
                        pg = await ctx.new_page()
                        await pg.goto(f"{base}/{lang}/{path}")
                        if "eventos/" in path:
                            await pg.click("#chat-open")
                            await pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                        await pg.add_script_tag(content=axe)
                        res = await pg.evaluate(
                            "async (rules) => (await axe.run(document, {runOnly: {type: 'tag', values: rules}}))"
                            ".violations.map(v => ({id: v.id, impact: v.impact, n: v.nodes.length,"
                            " target: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))", RULES)
                        checked += 1
                        if res:
                            total += len(res)
                            print(scheme, width, lang, path, json.dumps(res, ensure_ascii=False))
                        await pg.close()
                await ctx.close()
        await b.close()
    print(f"pages checked: {checked}; violations: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--axe", required=True)
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.axe, a.base, a.chrome)))
