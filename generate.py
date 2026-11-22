#!/usr/bin/env python3
"""Daily sarcasm lines for Daywall: Spanish headlines in, lines.json out."""
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

FEEDS = {
    "El País": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/espana/portada",
    "La Vanguardia": "https://www.lavanguardia.com/rss/politica.xml",
    "20minutos": "https://www.20minutos.es/rss/nacional/",
    "El Mundo": "https://e00-elmundo.uecdn.es/elmundo/rss/espana.xml",
    "elDiario.es": "https://www.eldiario.es/rss/politica/",
    "ABC": "https://www.abc.es/rss/2.0/espana/",
}
MODEL = "claude-opus-5-5"
OUT = Path(__file__).with_name("lines.json")

SYSTEM_PROMPT = """You write the daily one-liners for a kitchen wall display in a home in Catalonia, Spain. Each line is a single dry, sarcastic sentence about Spanish or Catalan politics, shown under the clock all day. The household reads it over breakfast: it should earn a smirk, not start an argument.

You are given today's headlines from several Spanish newspapers of different political leanings. Write 6 lines in Spanish ("es") and 6 in English ("en"). The English lines are for English speakers living in Spain: the same events, written natively in English, not translated word for word.

Rules:
- Base each line on something in today's headlines, or on a long-running situation they touch (budgets, commuter trains, housing, regional financing, coalition arithmetic). Never invent an event, a quote or an accusation.
- Aim at institutions, parties, processes and the general spectacle. You may name a party or an office ("the government", "Congress", "the Generalitat"). Do not name individual people: a line mocking a named person can be defamatory, or simply cruel on a wall that children read.
- Spread the mockery. Across the 6 lines, no party or side of the political spectrum is the target more than twice, and national and Catalan politics both appear when the headlines allow.
- Skip entirely any story involving death, violence, terrorism, sexual offences, accidents, disasters, illness, or court cases about private individuals. If such events dominate the day, write lines about the long-running situations instead.
- No slurs, no jokes about nationality, ethnicity, religion, gender, sexuality or disability, no profanity.
- Each line is one sentence of at most 110 characters, understandable without having read the article. Deadpan, like a weather forecast or a train announcement. No hashtags, no emoji, no exclamation marks."""


def fetch_headlines() -> dict[str, list[str]]:
    got = {}
    for name, url in FEEDS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "feed-reader/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                items = ET.fromstring(r.read()).iter("item")
            titles = [t.strip() for i in items if (t := i.findtext("title"))]
            if titles:
                got[name] = titles[:15]
        except Exception as e:
            print(f"skipped {name}: {e}", file=sys.stderr)
    if len(got) < 3:
        sys.exit(f"only {len(got)} feeds succeeded, need at least 3")
    return got


def validate(lines: dict) -> None:
    for lang in ("en", "es"):
        ls = lines[lang]
        if not 4 <= len(ls) <= 8:
            raise ValueError(f"{lang}: {len(ls)} lines, need 4 to 8")
        for l in ls:
            if not l.strip() or len(l) > 120:
                raise ValueError(f"{lang}: empty or over 120 characters: {l!r}")


def main() -> None:
    headlines = fetch_headlines()
    if "--headlines" in sys.argv[1:]:
        for name, titles in headlines.items():
            print(f"\n{name} ({len(titles)})")
            print("\n".join(f"  {t}" for t in titles))
        print(f"\n{len(headlines)} of {len(FEEDS)} feeds succeeded")
        return

    import anthropic
    from pydantic import BaseModel

    class Lines(BaseModel):
        en: list[str]
        es: list[str]

    today = date.today().isoformat()
    body = "\n\n".join(f"{n}:\n" + "\n".join(f"- {t}" for t in ts) for n, ts in headlines.items())
    try:
        r = anthropic.Anthropic().messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Today is {today}.\n\nHeadlines:\n\n{body}"}],
            output_config={"effort": "medium"},
            output_format=Lines,
        )
        if r.stop_reason == "refusal":
            sys.exit(f"refused: {r.stop_details}")
        if r.parsed_output is None:
            sys.exit(f"no structured output (stop_reason={r.stop_reason})")
        lines = r.parsed_output.model_dump()
        validate(lines)
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"failed: {e}")
    OUT.write_text(json.dumps({"date": today, **lines}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
