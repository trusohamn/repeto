"""Build podcast RSS feeds from course catalogs using only the standard library."""

import argparse
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import quote

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
CONTENT = "http://purl.org/rss/1.0/modules/content/"
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)
ET.register_namespace("content", CONTENT)
FINGERPRINT = re.compile(r"-[0-9a-f]{8}")
LIST_ITEM = re.compile(r"(?:•|\d+\.)\s+")
STYLE = (
    "body{font-family:system-ui,sans-serif;max-width:42rem;margin:auto;padding:1rem;"
    "line-height:1.5;color:#222}img{max-width:100%;height:auto;border-radius:.5rem}"
    "audio{width:100%}details{margin:.75rem 0;border-bottom:1px solid #ddd;"
    "padding-bottom:.75rem}summary{cursor:pointer;font-weight:600}"
    ".card{display:flex;gap:1rem;margin:1.5rem 0}.card img{width:8rem;flex:none}"
)
HOME_STYLE = """
:root{color-scheme:light;--ink:#182849;--muted:#536570;--paper:#fbf8f2;--accent:#b9232a;
--logo-red:#f02b32;--logo-yellow:#fec607;--logo-green:#65bb40;--logo-blue:#439dd8;
--logo-pink:#fc4c9d;--logo-purple:#a04bcd;
--rainbow:linear-gradient(90deg,var(--logo-red) 0% 16.67%,var(--logo-yellow) 16.67% 33.33%,
var(--logo-green) 33.33% 50%,var(--logo-blue) 50% 66.67%,var(--logo-pink) 66.67% 83.33%,
var(--logo-purple) 83.33% 100%)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font-family:system-ui,sans-serif;line-height:1.6}
a{color:inherit}a:focus-visible{outline:3px solid var(--accent);outline-offset:5px}
.shell{max-width:1160px;margin:auto;padding:0 28px}.skip{position:absolute;left:24px;top:-100px}
.skip:focus{top:12px;background:white;padding:12px;z-index:2}
header{display:flex;justify-content:space-between;align-items:center;padding:24px 0}
.brand{display:inline-block;font-size:1.6rem;font-weight:900;letter-spacing:-.06em;text-decoration:none}
.hero{padding:24px 0 36px;max-width:820px}
.hero::after{content:"";display:block;width:180px;height:6px;background:var(--rainbow);
border-radius:100px;margin-top:24px}
h1{font-size:clamp(2.7rem,7vw,5.3rem);line-height:1.05;letter-spacing:-.065em;margin:16px 0 24px}
h1 span{color:var(--accent);text-decoration:underline;text-decoration-color:var(--logo-yellow);
text-decoration-thickness:6px;text-underline-offset:8px}
.hero p{font-size:1.15rem;max-width:580px;color:var(--muted)}
.language-label{font-weight:650;margin:0 0 12px}
.language-nav{display:flex;gap:10px;flex-wrap:wrap;padding:0 0 30px}
.language-nav a{border:1px solid #c7cec9;border-radius:100px;padding:9px 20px;text-decoration:none;font-weight:650}
.language-nav a:nth-child(4n+1){background:#e0efdf;border-color:var(--logo-green)}
.language-nav a:nth-child(4n+2){background:#fff0ce;border-color:var(--logo-yellow)}
.language-nav a:nth-child(4n+3){background:#e0eafa;border-color:var(--logo-blue)}
.language-nav a:nth-child(4n+4){background:#f0e1f3;border-color:var(--logo-purple)}
.language-nav a:hover{background:var(--ink);color:white;border-color:var(--ink)}
.course-section{padding:28px 0 36px;scroll-margin-top:16px;border-top:1px solid #dedfd5}
.section-heading{margin-bottom:24px}
h2{font-size:1.65rem;letter-spacing:-.035em;margin:0}
.course-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px}
.course-card{background:white;border:1px solid #e3e4dc;border-radius:22px;overflow:hidden;box-shadow:0 5px 20px #182b3907}
.cover-link{display:block;overflow:hidden;background:#eee}.cover-link img{display:block;width:100%;aspect-ratio:1;object-fit:cover}
.card-body{padding:20px}.course-card h3{font-size:1.28rem;margin:0 0 8px;letter-spacing:-.025em}
.course-card h3 a{text-decoration:none}.course-card h3 a:hover{text-decoration:underline}
.episode-count{font-size:.85rem;color:var(--muted);margin:0 0 18px}
.platform-links{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.platform-links a{border:1px solid #c7cec9;border-radius:100px;padding:7px 13px;
font-size:.85rem;font-weight:650;text-decoration:none}
.platform-links a:hover{background:var(--ink);color:white;border-color:var(--ink)}
.platform-links .spotify-link{color:#176c38;background:#e0efdf}
.platform-links .youtube-link{color:#a52e20;background:#ffe6df}
.platform-links a:hover{background:var(--ink);color:white}
.youtube-notice{background:#fff0ce;border-radius:16px;padding:16px 24px;margin:0 0 30px}
.youtube-notice p{margin:6px 0 0;color:var(--muted)}
.closing{background:#e0efdf;color:var(--ink);border-radius:24px;padding:32px;margin:20px 0 40px}
.closing h2{font-size:1.8rem}.closing p{max-width:650px;margin-bottom:0;color:var(--muted)}
.podcast-apps{margin:0 0 32px;color:var(--muted);font-size:.9rem}
.podcast-apps summary{cursor:pointer;font-weight:650}.podcast-apps ul{padding-left:20px}
footer{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;border-top:1px solid #dedfd5;
padding:24px 0 36px;font-size:.8rem;color:var(--muted)}
@media(max-width:850px){.course-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:540px){.shell{padding:0 20px}
.hero{padding-top:24px}.course-grid{grid-template-columns:1fr}.closing{padding:24px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""
HOME_AUDIENCES = {
    "sv": ("Swedish", "For Swedish speakers"),
    "pl": ("Polish", "For Polish speakers"),
    "en": ("English", "For English speakers"),
    "ru": ("Russian", "For Russian speakers"),
}


def text_to_html(text: str) -> str:
    """Render plain description text: blank lines split paragraphs, • or N. lines form lists."""
    blocks = []
    for paragraph in text.strip().split("\n\n"):
        lines = paragraph.splitlines()
        heading = [line for line in lines if not LIST_ITEM.match(line)]
        items = [LIST_ITEM.sub("", line, count=1) for line in lines if LIST_ITEM.match(line)]
        if heading and not items:
            blocks.append("<p>" + "<br>".join(html.escape(line) for line in lines) + "</p>")
            continue
        if heading:
            blocks.append("<p>" + "<br>".join(html.escape(line) for line in heading) + "</p>")
        tag = "ol" if LIST_ITEM.match(lines[-1]) and lines[-1][0].isdigit() else "ul"
        blocks.append(
            f"<{tag}>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + f"</{tag}>"
        )
    return "".join(blocks)


def _page(title: str, body: str, language: str = "sv", *, style: str = STYLE) -> str:
    return (
        f'<!doctype html><html lang="{html.escape(language, quote=True)}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{style}</style>{body}</html>\n"
    )


def _fingerprinted_versions(path: Path) -> list[Path]:
    return sorted(
        candidate for candidate in path.parent.glob(f"{path.stem}-*{path.suffix}")
        if FINGERPRINT.fullmatch(candidate.stem[len(path.stem):])
    )


def find_image(path: Path) -> Path | None:
    """Return the file currently published for a logical image path such as cover.jpeg."""
    if path.is_file():
        return path
    versions = _fingerprinted_versions(path)
    if len(versions) > 1:
        raise ValueError(f"Several published versions of {path.name}: {versions}")
    return versions[0] if versions else None


def fingerprint_image(path: Path) -> Path:
    """Publish an image under a content-hashed name so podcast apps fetch new artwork.

    A plain file (for example a newly dropped-in cover.jpeg) replaces older
    fingerprinted versions; only the current version is kept on disk.
    """
    current = find_image(path)
    if current is None or current.stat().st_size == 0:
        raise ValueError(f"Missing or empty image: {path}")
    digest = hashlib.sha256(current.read_bytes()).hexdigest()[:8]
    published = path.with_name(f"{path.stem}-{digest}{path.suffix}")
    if current != published:
        current.replace(published)
    for stale in _fingerprinted_versions(path):
        if stale != published:
            stale.unlink()
    return published


def remove_superseded_audio(course: Path, old_files: list[str]) -> list[Path]:
    """Delete episode MP3s that a re-render replaced and the catalog no longer uses."""
    catalog = json.loads((course / "course.json").read_text(encoding="utf-8"))
    referenced = {episode["file"] for episode in catalog["episodes"]}
    audio_root = (course / "audio").resolve()
    removed = []
    for old_file in sorted(set(old_files) - referenced):
        path = (audio_root / Path(*PurePosixPath(old_file).parts)).resolve()
        if path.parent.is_relative_to(audio_root) and path.is_file():
            path.unlink()
            removed.append(path)
    return removed


def build_feed(course: Path, base_url: str) -> None:
    config = json.loads((course / "course.json").read_text(encoding="utf-8"))
    url = f"{base_url.rstrip('/')}/{quote(course.name)}"
    if not base_url.startswith("https://"):
        raise ValueError("Podcast hosting requires an HTTPS base URL.")
    if find_image(course / "cover.jpeg") is None:
        raise ValueError(f"Missing cover: {course}")
    episodes = config["episodes"]
    if not episodes:
        raise ValueError(f"No episodes: {course}")
    cover = fingerprint_image(course / "cover.jpeg")
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    def field(parent: ET.Element, name: str, text: str) -> ET.Element:
        element = ET.SubElement(parent, name)
        element.text = text
        return element

    field(channel, "title", config["title"])
    field(channel, "link", url + "/")
    field(channel, "description", config["description"])
    field(channel, "language", config["language"])
    field(channel, f"{{{ITUNES}}}author", config["author"])
    field(channel, f"{{{ITUNES}}}explicit", "false")
    field(channel, f"{{{ITUNES}}}type", "serial")
    owner = ET.SubElement(channel, f"{{{ITUNES}}}owner")
    field(owner, f"{{{ITUNES}}}name", config["author"])
    field(owner, f"{{{ITUNES}}}email", config["email"])
    ET.SubElement(channel, f"{{{ITUNES}}}image", href=url + "/" + quote(cover.name))
    category = ET.SubElement(channel, f"{{{ITUNES}}}category", text="Education")
    ET.SubElement(category, f"{{{ITUNES}}}category", text="Language Learning")
    ET.SubElement(
        channel, f"{{{ATOM}}}link", href=url + "/feed.xml",
        rel="self", type="application/rss+xml",
    )
    seen = set()
    seen_numbers = set()
    for episode in episodes:
        season = episode["season"]
        number = episode["episode"]
        if (
            type(season) is not int or season < 1
            or type(number) is not int or number < 1
        ):
            raise ValueError("Season and episode numbers must be positive integers.")
        if (season, number) in seen_numbers:
            raise ValueError(f"Duplicate season/episode: {season}/{number}")
        seen_numbers.add((season, number))
        filename = episode["file"]
        if not isinstance(filename, str):
            raise ValueError(f"Invalid audio filename: {filename!r}")
        relative_audio_path = PurePosixPath(filename)
        if (
            "\\" in filename
            or relative_audio_path.is_absolute()
            or str(relative_audio_path) != filename
            or any(part in {"", ".", ".."} for part in relative_audio_path.parts)
            or relative_audio_path.suffix != ".mp3"
        ):
            raise ValueError(f"Invalid audio filename: {filename!r}")
        audio = course / "audio" / Path(*relative_audio_path.parts)
        if not audio.is_file() or audio.stat().st_size == 0:
            raise ValueError(f"Missing or empty audio: {audio}")
        if episode["id"] in seen:
            raise ValueError(f"Duplicate episode ID: {episode['id']}")
        seen.add(episode["id"])
        item = ET.SubElement(channel, "item")
        title = f"{number:02d} {episode['title']}"
        field(item, "title", title)
        field(item, "description", episode["description"])
        field(item, f"{{{CONTENT}}}encoded", text_to_html(episode["description"]))
        guid = field(item, "guid", episode["id"])
        guid.set("isPermaLink", "false")
        field(item, "pubDate", format_datetime(datetime.fromisoformat(episode["published"])))
        field(item, f"{{{ITUNES}}}episode", str(number))
        field(item, f"{{{ITUNES}}}season", str(season))
        field(item, f"{{{ITUNES}}}episodeType", "full")
        field(item, f"{{{ITUNES}}}duration", str(round(episode["duration_ms"] / 1000)))
        field(item, f"{{{ITUNES}}}explicit", "false")
        if "image" in episode:
            image_name = episode["image"]
            if not isinstance(image_name, str) or not image_name:
                raise ValueError(f"Invalid episode image: {image_name!r}")
            relative_image_path = PurePosixPath(image_name)
            if (
                "\\" in image_name
                or ":" in image_name
                or relative_image_path.is_absolute()
                or str(relative_image_path) != image_name
                or any(part in {"", ".", ".."} for part in relative_image_path.parts)
                or relative_image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}
            ):
                raise ValueError(f"Invalid episode image: {image_name!r}")
            logical_image = course / Path(*relative_image_path.parts)
            published_image = find_image(logical_image)
            if published_image is None or published_image.stat().st_size == 0:
                raise ValueError(f"Missing or empty episode image: {logical_image}")
            image = fingerprint_image(logical_image)
            published_parts = (*relative_image_path.parts[:-1], image.name)
            ET.SubElement(
                item, f"{{{ITUNES}}}image",
                href=url + "/" + "/".join(quote(part) for part in published_parts),
            )
        ET.SubElement(
            item, "enclosure",
            url=url + "/audio/" + "/".join(
                quote(part) for part in relative_audio_path.parts
            ),
            length=str(audio.stat().st_size), type="audio/mpeg",
        )
    ET.indent(rss)
    ET.ElementTree(rss).write(course / "feed.xml", encoding="utf-8", xml_declaration=True)
    cover_label, listen_label, season_label, rss_label = {
        "pl": ("Okładka", "Słuchaj", "Sezon", "Kanał RSS"),
        "en": ("Cover", "Listen", "Season", "RSS feed"),
        "ru": ("Обложка", "Слушать", "Сезон", "RSS-лента"),
    }.get(config["language"], ("Omslag", "Lyssna", "Säsong", "RSS-flöde"))
    links = [
        f'<a href="{html.escape(link_url)}">{html.escape(name)}</a>'
        for name, link_url in config.get("links", {}).items()
    ] + [f'<a href="feed.xml">{rss_label}</a>']
    seasons: dict[int, list[str]] = {}
    season_names: dict[str, str] = config.get("seasons", {})
    for episode in sorted(episodes, key=lambda e: (e["season"], e["episode"])):
        audio_url = "audio/" + "/".join(
            quote(part) for part in PurePosixPath(episode["file"]).parts
        )
        seasons.setdefault(episode["season"], []).append(
            f'<details><summary>{episode["episode"]:02d} '
            f'{html.escape(episode["title"])}</summary>'
            f'{text_to_html(episode["description"])}'
            f'<audio controls preload="none" src="{html.escape(audio_url)}"></audio></details>'
        )
    (course / "index.html").write_text(_page(config["title"], (
        f'<h1>{html.escape(config["title"])}</h1>'
        f'<img src="{html.escape(quote(cover.name))}" alt="{cover_label}" width="300">'
        f'{text_to_html(config["description"])}'
        f'<p><strong>{listen_label}:</strong> {" · ".join(links)}</p>'
        + "".join(
            f"<h2>{season_label} {season}"
            + (f" – {html.escape(name)}" if (name := season_names.get(str(season))) else "")
            + f"</h2>{''.join(items)}"
            for season, items in seasons.items()
        )
    ), language=config["language"]), encoding="utf-8")


def build_index(root: Path, courses: list[Path]) -> None:
    groups: dict[str, list[str]] = {}
    feed_links = []
    for course in courses:
        config = json.loads((course / "course.json").read_text(encoding="utf-8"))
        language = config["language"]
        if language not in HOME_AUDIENCES:
            raise ValueError(f"Unsupported homepage audience: {language!r}")
        cover = find_image(course / "cover.jpeg")
        if cover is None:
            raise ValueError(f"Missing cover: {course}")
        href = quote(course.name) + "/"
        title = html.escape(config["title"].removeprefix("Repeto – "))
        feed_links.append(
            f'<li lang="{language}"><a href="{href}feed.xml">{title}</a></li>'
        )
        spotify = config.get("links", {}).get("Spotify")
        youtube = config.get("links", {}).get("YouTube")
        if youtube and re.fullmatch(
            r"https://www\.youtube\.com/playlist\?list=PL[A-Za-z0-9_-]{10,}", youtube
        ) is None:
            raise ValueError(f"Invalid YouTube playlist URL for {course.name}: {youtube!r}")
        destination = html.escape(spotify or youtube or href, quote=True)
        platform_links = []
        if spotify:
            match = re.fullmatch(r"https://open\.spotify\.com/show/([A-Za-z0-9]{22})", spotify)
            if match is None:
                raise ValueError(f"Invalid Spotify show URL for {course.name}: {spotify!r}")
            platform_links.append(
                f'<a class="spotify-link" href="{html.escape(spotify, quote=True)}">'
                'Open in Spotify</a>'
            )
        if youtube:
            platform_links.append(
                f'<a class="youtube-link" href="{html.escape(youtube, quote=True)}">'
                'Listen on YouTube</a>'
            )
        platforms = (
            f'<div class="platform-links">{"".join(platform_links)}</div>'
            if platform_links else ""
        )
        groups.setdefault(language, []).append(
            f'<article class="course-card"><a class="cover-link" href="{destination}" tabindex="-1" '
            f'aria-hidden="true"><img src="{href}{quote(cover.name)}" alt="" '
            'width="400" height="400" loading="lazy"></a><div class="card-body">'
            f'<h3 lang="{language}"><a href="{destination}">{title}</a></h3>'
            f'<p class="episode-count">{len(config["episodes"])} episodes</p>'
            f'{platforms}</div></article>'
        )
    navigation = []
    sections = []
    for language, (label, heading) in HOME_AUDIENCES.items():
        if language not in groups:
            continue
        navigation.append(f'<a href="#courses-{language}">{label}</a>')
        sections.append(
            f'<section class="course-section" id="courses-{language}" '
            f'aria-labelledby="heading-{language}"><div class="section-heading">'
            f'<h2 id="heading-{language}">{heading}</h2></div>'
            f'<div class="course-grid">{"".join(groups[language])}</div></section>'
        )
    body = (
        '<a class="skip" href="#courses">Skip to courses</a><div class="shell">'
        '<header><a class="brand" href="./">Repeto</a></header><main>'
        '<section class="hero" aria-labelledby="welcome">'
        '<h1 id="welcome">Learn a language.<br><span>Without the screen.</span></h1>'
        '<p>Little language adventures for kids, grown-ups, and anyone starting out. '
        'Press play in your podcast app, put the screen away, and learn by listening '
        'and speaking — together at the kitchen table or on a walk of your own. It’s free.</p>'
        '<p>Hear a phrase in your language, try saying it in the new one, '
        'then listen to the answer and repeat.</p>'
        '</section>'
        '<aside class="youtube-notice" aria-label="YouTube availability">'
        '<strong>Repeto is coming to YouTube, too.</strong>'
        '<p>Uploads are in progress. YouTube links appear below as playlists become available; '
        'not all episodes or courses are there yet. '
        '<a href="https://www.youtube.com/@repeto-ling/podcasts">Browse our YouTube podcasts</a>.'
        '</p></aside>'
        '<div id="courses"><p class="language-label" id="native-language">Choose your native language:</p>'
        '<nav class="language-nav" aria-labelledby="native-language">'
        + "".join(navigation) + '</nav>' + "".join(sections)
        + '</div><section class="closing"><h2>From your first words to a little adventure.</h2>'
        '<p>Start with everyday words, then meet a mysterious radio in our eight-part story. '
        'Listen to a chapter, try its words, and hear it again. '
        'Go at your own pace, together or on your own.</p>'
        '</section><details class="podcast-apps"><summary>Other podcast apps</summary>'
        '<p>To subscribe in another podcast app, copy a feed link below and paste it '
        'into the app’s “add podcast by URL” option. These links are feeds, not listening pages.</p>'
        f'<ul>{"".join(feed_links)}</ul></details></main>'
        '<footer><span>Repeto · AI-generated voices (Microsoft Azure)</span>'
        '<a href="mailto:repeto.lingo@gmail.com">repeto.lingo@gmail.com</a></footer></div>'
    )
    (root / "index.html").write_text(
        _page("Repeto – screen-free language learning", body, language="en", style=HOME_STYLE),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("podcast"))
    parser.add_argument("--base-url", default="https://trusohamn.github.io/repeto")
    args = parser.parse_args()
    courses = sorted(path.parent for path in args.root.glob("*/course.json"))
    if not courses:
        raise ValueError("No course catalogs found.")
    for course in courses:
        build_feed(course, args.base_url)
    build_index(args.root, courses)
    (args.root / ".nojekyll").touch()


if __name__ == "__main__":
    main()
