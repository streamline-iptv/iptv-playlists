"""Build the Doubo public channel directory from iptv-org data.

Domain model
------------
Channel   a TV channel from iptv-org/database (id, country, categories, website).
Feed      a variant of a channel (SD/HD/regional) carrying its languages.
Stream    a URL from one of the sources (iptv-org/iptv, other curated lists in
          sources.yml, or streams found by scripts/discover.py), pointing at one channel feed.
Policy    decides whether a stream may be listed. Only streams served from one of
          the channel's own domains (its website's, plus policy/official-domains.csv)
          or from an allowlisted broadcast CDN / official FAST platform pass; links on a
          redirect service (policy/redirectors.txt) are judged by where they land.
Playlist  a named selection of listed streams (all, per country, per category,
          per language), written as M3U plus a JSON index for the website.

Usage: python scripts/build.py --data DATA_DIR --streams STREAMS_DIR --out OUT_DIR [--probe]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import fnmatch
import ipaddress
import json
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import tldextract
import yaml

ROOT = Path(__file__).resolve().parent.parent
_extract = tldextract.TLDExtract(suffix_list_urls=())  # bundled public suffix list, no network


# ---------------------------------------------------------------- domain

@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    country: str
    categories: tuple[str, ...]
    website: str
    is_nsfw: bool
    closed: bool


@dataclass(frozen=True)
class Feed:
    channel_id: str
    id: str
    is_main: bool
    languages: tuple[str, ...]


@dataclass
class Stream:
    channel_id: str
    feed_id: str
    title: str
    url: str
    options: list[str] = field(default_factory=list)  # #EXTVLCOPT lines (referrer, user agent)
    source: str = "iptv-org"
    # For a redirect link that refused us (geo-locked): the platform domain it is known to land
    # on (policy/redirectors.txt). The policy judges that domain instead of the redirector's.
    lands_on: str | None = None

    @property
    def geo_blocked(self) -> bool:
        return "[Geo-blocked]" in self.title

    @property
    def host_domain(self) -> str | None:
        return self.lands_on or registrable_domain(self.url)


def registrable_domain(url: str) -> str | None:
    host = urlsplit(url).hostname or ""
    try:
        ipaddress.ip_address(host)
        return None  # bare IPs are never a broadcaster's official endpoint
    except ValueError:
        pass
    return _extract(host).top_domain_under_public_suffix or None


class Policy:
    def __init__(
        self,
        allowed_hosts: set[str],
        blocked_channels: set[str],
        takedowns: set[str],
        official_domains: dict[str, set[str]] | None = None,
        blocked_hosts: set[str] | None = None,
    ):
        self.allowed_hosts = allowed_hosts
        self.blocked_channels = blocked_channels
        self.takedowns = takedowns
        self.official_domains = official_domains or {}  # channel id -> other domains its broadcaster owns
        self.blocked_hosts = blocked_hosts or set()  # hostname patterns of paid operators / aggregators

    @classmethod
    def load(cls, data: Path) -> Policy:
        """The policy in policy/ plus the iptv-org blocklist from DATABASE_DATA_DIR."""
        official: dict[str, set[str]] = defaultdict(set)
        for r in read_csv(ROOT / "policy" / "official-domains.csv"):
            official[r["channel"]].add(r["domain"])
        return cls(
            allowed_hosts=load_lines(ROOT / "policy" / "allowed-hosts.txt"),
            blocked_channels={r["channel"] for r in read_csv(data / "blocklist.csv")},
            takedowns={r["target"] for r in read_csv(ROOT / "policy" / "takedown.csv")},
            official_domains=official,
            blocked_hosts=load_lines(ROOT / "policy" / "blocked-hosts.txt"),
        )

    def own_domains(self, channel: Channel) -> set[str]:
        """Domains run by the channel's broadcaster: its website's domain plus policy/official-domains.csv."""
        website = registrable_domain(channel.website) if channel.website else None
        return self.official_domains.get(channel.id, set()) | ({website} if website else set())

    def is_official(self, stream: Stream, channel: Channel) -> bool:
        return stream.host_domain in self.own_domains(channel)

    def admits(self, stream: Stream, channel: Channel | None) -> bool:
        if channel is None or channel.is_nsfw or channel.closed or "xxx" in channel.categories:
            return False
        if channel.id in self.blocked_channels or channel.id in self.takedowns or stream.url in self.takedowns:
            return False
        if urlsplit(stream.url).scheme not in ("http", "https"):
            return False
        host = (urlsplit(stream.url).hostname or "").lower()
        if any(fnmatch.fnmatchcase(host, pattern) for pattern in self.blocked_hosts):
            return False
        domain = stream.host_domain
        if domain is None:
            return False
        return domain in self.own_domains(channel) or domain in self.allowed_hosts


# ---------------------------------------------------------------- loading

def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def split(value: str) -> tuple[str, ...]:
    return tuple(v for v in value.split(";") if v)


def load_channels(data: Path) -> dict[str, Channel]:
    return {
        r["id"]: Channel(
            id=r["id"], name=r["name"], country=r["country"], categories=split(r["categories"]),
            website=r["website"], is_nsfw=r["is_nsfw"] == "TRUE", closed=bool(r["closed"]),
        )
        for r in read_csv(data / "channels.csv")
    }


def load_feeds(data: Path) -> dict[tuple[str, str], Feed]:
    feeds = {}
    for r in read_csv(data / "feeds.csv"):
        feed = Feed(r["channel"], r["id"], r["is_main"] == "TRUE", split(r["languages"]))
        feeds[(feed.channel_id, feed.id)] = feed
    return feeds


def load_logos(data: Path) -> dict[tuple[str, str], str]:
    logos: dict[tuple[str, str], str] = {}
    for r in read_csv(data / "logos.csv"):
        logos.setdefault((r["channel"], r["feed"]), r["url"])
    return logos


def load_lines(path: Path) -> set[str]:
    return {l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


MARKERS = re.compile(r"[\u24b6-\u24e9]")  # circled-letter flags some lists append to titles


def parse_playlist(text: str, source: str) -> list[Stream]:
    """Streams of one M3U playlist. Free-TV style markers are stripped from titles; its
    geo-block marker (Ⓖ) becomes the "[Geo-blocked]" label the probe understands."""
    streams = []
    pending: Stream | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF"):
            tvg_id = re.search(r'tvg-id="([^"]*)"', line)
            channel_id, _, feed_id = (tvg_id.group(1) if tvg_id else "").partition("@")
            title = line.rsplit(",", 1)[-1].strip()
            if "\u24bc" in title and "[Geo-blocked]" not in title:
                title += " [Geo-blocked]"
            title = re.sub(r"\s+", " ", MARKERS.sub("", title)).strip()
            pending = Stream(channel_id, feed_id, title, "", source=source)
        elif line.startswith("#EXTVLCOPT") and pending:
            pending.options.append(line)
        elif line and not line.startswith("#") and pending:
            pending.url = line
            streams.append(pending)
            pending = None
    return streams


def parse_streams(streams_dir: Path) -> list[Stream]:
    streams = []
    for path in sorted(streams_dir.glob("*.m3u")):
        streams += parse_playlist(path.read_text(encoding="utf-8", errors="replace"), "iptv-org")
    return streams


def load_sources(registry: Path) -> list[Stream]:
    """Additional playlists from sources.yml: remote curated lists and the discovered list."""
    streams = []
    for src in yaml.safe_load(registry.read_text(encoding="utf-8"))["sources"]:
        if not src.get("enabled", True) or src["id"] == "iptv-org":
            continue
        try:
            if src.get("path"):
                text = (ROOT / src["path"]).read_text(encoding="utf-8")
            else:
                request = urllib.request.Request(src["url"], headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=60) as response:
                    text = response.read().decode("utf-8", errors="replace")
        except OSError as error:
            print(f"source {src['id']} skipped: {error}")
            continue
        found = parse_playlist(text, src["id"])
        print(f"source {src['id']}: {len(found)} entries")
        streams += found
    return streams


# ---------------------------------------------------------------- probing

USER_AGENT = "Mozilla/5.0 (Doubo directory check)"
MAX_PLAYLIST_BYTES = 512 * 1024


def request_headers(stream: Stream) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    for opt in stream.options:
        key, _, value = opt.removeprefix("#EXTVLCOPT:").partition("=")
        headers[{"http-referrer": "Referer", "http-user-agent": "User-Agent"}.get(key, key)] = value
    return headers


def fetch(url: str, headers: dict[str, str], limit: int, timeout: float) -> tuple[str, bytes]:
    """Return the final URL (after redirects) and up to `limit` bytes of the body."""
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 400:
            raise OSError(response.status)
        return response.geturl(), response.read(limit)


def looks_like_media(data: bytes) -> bool:
    """MPEG-TS, fragmented MP4, or audio-only (ID3 / ADTS) segment."""
    if len(data) >= 189 and data[0] == 0x47 and data[188] == 0x47:
        return True
    if data[4:8] in (b"ftyp", b"styp", b"moof", b"sidx", b"moov"):
        return True
    return data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xF0 == 0xF0)


def first_uri(playlist: str, base: str) -> str | None:
    for line in playlist.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return urljoin(base, line)
    return None


def probe(stream: Stream, timeout: float = 10) -> bool:
    """Follow the stream the way a player would: master playlist, then a variant,
    then the first media segment, and check that the segment is real audio/video."""
    headers = request_headers(stream)
    try:
        url, body = fetch(stream.url, headers, MAX_PLAYLIST_BYTES, timeout)
        for _ in range(3):  # master -> variant -> (rarely) one more redirect playlist
            if looks_like_media(body):
                return True
            text = body.decode("utf-8", errors="replace")
            if "<MPD" in text:
                return True  # DASH manifest; segment templates are not resolved here
            if not text.lstrip("\ufeff").startswith("#EXTM3U"):
                return False
            next_url = first_uri(text, url)
            if next_url is None:
                return False
            is_segment = "#EXT-X-STREAM-INF" not in text
            if is_segment and re.search(r"#EXT-X-KEY:.*METHOD=(AES-128|SAMPLE-AES)", text):
                fetch(next_url, headers, 1024, timeout)
                return True  # encrypted segments cannot be inspected, but they are served
            url, body = fetch(next_url, headers, 4096 if is_segment else MAX_PLAYLIST_BYTES, timeout)
            if is_segment:
                return looks_like_media(body)
        return False
    except Exception:
        return False


@dataclass(frozen=True)
class Redirectors:
    """policy/redirectors.txt: redirect services, and the platform each link prefix lands on."""
    domains: frozenset[str]
    lands_on: tuple[tuple[str, str], ...]  # (URL prefix without scheme, platform domain)

    @classmethod
    def load(cls, path: Path) -> Redirectors:
        domains, lands_on = set(), []
        for line in load_lines(path):
            target, _, platform = line.partition(" ")
            if platform.strip():
                lands_on.append((target, platform.strip()))
            domains.add(target.split("/")[0])
        return cls(frozenset(domains), tuple(lands_on))

    def platform_of(self, url: str) -> str | None:
        bare = url.split("://", 1)[-1]
        return next((platform for prefix, platform in self.lands_on if bare.startswith(prefix)), None)


def resolve_redirects(streams: list[Stream], redirectors: Redirectors, workers: int = 16) -> list[Stream]:
    """Replace each stream on a redirect service with the address it lands on, so the policy
    judges, and the playlist lists, the real host. A link the service refuses with 403 (it is
    geo-locked to another region) is kept as is, labelled geo-blocked and judged by the platform
    its prefix is known to land on; other failures and redirect loops are dropped."""
    failures: Counter[str] = Counter()
    landed: Counter[str] = Counter()
    kept_geo: Counter[str] = Counter()

    def resolve(s: Stream) -> Stream | None:
        try:
            final, _ = fetch(s.url, request_headers(s), 0, 10)
        except urllib.error.HTTPError as error:
            failures[f"HTTP {error.code}"] += 1
            platform = redirectors.platform_of(s.url)
            if error.code == 403 and platform:
                kept_geo[platform] += 1
                title = s.title if s.geo_blocked else f"{s.title} [Geo-blocked]"
                return replace(s, title=title, lands_on=platform)
            return None
        except Exception as error:
            failures[type(getattr(error, "reason", error)).__name__] += 1
            return None
        domain = registrable_domain(final)
        if domain in redirectors.domains:
            failures["redirect loop"] += 1
            return None
        landed[domain or "bare IP"] += 1
        return replace(s, url=final)

    via = [s for s in streams if registrable_domain(s.url) in redirectors.domains]
    if not via:
        return streams
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        resolved = dict(zip(map(id, via), pool.map(resolve, via)))
    print(f"redirects: {sum(landed.values())}/{len(via)} resolved, {sum(kept_geo.values())} kept as geo-blocked")
    print(f"  landed on: {dict(landed.most_common(8))}")
    print(f"  failed: {dict(failures.most_common(8))}")
    print(f"  refused (403), kept as geo-blocked: {dict(kept_geo.most_common(8))}")
    kept = []
    for s in streams:
        target = resolved.get(id(s), s)
        if target is not None:
            kept.append(target)
    return kept


def keep_playable(streams: list[Stream], workers: int = 64) -> list[Stream]:
    # Geo-blocked streams cannot be checked from a CI runner, so they are kept as listed.
    to_check = [s for s in streams if not s.geo_blocked]
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        playable = {id(s) for s, ok in zip(to_check, pool.map(probe, to_check)) if ok}
    print(f"check: {len(playable)}/{len(to_check)} playable, {len(streams) - len(to_check)} geo-blocked kept unchecked")
    return [s for s in streams if s.geo_blocked or id(s) in playable]


# ---------------------------------------------------------------- output

@dataclass
class Entry:
    stream: Stream
    channel: Channel
    languages: tuple[str, ...]
    logo: str

    def m3u(self) -> str:
        attrs = {
            "tvg-id": f"{self.channel.id}@{self.stream.feed_id}" if self.stream.feed_id else self.channel.id,
            "tvg-logo": self.logo,
            "tvg-country": self.channel.country,
            "tvg-language": ";".join(self.languages),
            "group-title": ";".join(c.capitalize() for c in self.channel.categories) or "Undefined",
        }
        head = " ".join(f'{k}="{v}"' for k, v in attrs.items() if v)
        return "\n".join([f"#EXTINF:-1 {head},{self.stream.title}", *self.stream.options, self.stream.url])


# Programme guide for the directory's channel ids (XMLTV, gzipped), rebuilt daily by doubo.tv from the
# Pluto TV, Plex, Samsung TV Plus and Roku guides that i.mjh.nz republishes. Players that read the
# header (Doubo, TiviMate, VLC-based apps...) show what is on now and next.
GUIDE_URL = "https://doubo.tv/epg/doubo.xml.gz"


def write_playlist(path: Path, entries: list[Entry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(entries, key=lambda e: (e.stream.title.lower(), e.stream.url))
    header = f'#EXTM3U x-tvg-url="{GUIDE_URL}"\n'
    path.write_text(header + "".join(e.m3u() + "\n" for e in ordered), encoding="utf-8")


def build(data: Path, streams_dir: Path, out: Path, check: bool, registry: Path | None = None) -> dict:
    channels, feeds, logos = load_channels(data), load_feeds(data), load_logos(data)
    language_names = {r["code"]: r["name"] for r in read_csv(data / "languages.csv")}
    policy = Policy.load(data)
    candidates = parse_streams(streams_dir) + (load_sources(registry) if registry else [])
    # Only follow redirects for identified channels; the rest would be left out anyway.
    candidates = resolve_redirects(
        [s for s in candidates if s.channel_id in channels], Redirectors.load(ROOT / "policy" / "redirectors.txt")
    )
    listed = [s for s in candidates if policy.admits(s, channels.get(s.channel_id))]
    if check:
        listed = keep_playable(listed)

    entries = []
    seen_urls = set()
    for s in listed:
        if s.url in seen_urls:
            continue
        seen_urls.add(s.url)
        channel = channels[s.channel_id]
        feed = feeds.get((s.channel_id, s.feed_id))
        logo = logos.get((s.channel_id, s.feed_id)) or logos.get((s.channel_id, ""), "")
        entries.append(Entry(s, channel, feed.languages if feed else (), logo))

    by_country, by_category, by_language = defaultdict(list), defaultdict(list), defaultdict(list)
    for e in entries:
        by_country[e.channel.country.lower()].append(e)
        for c in e.channel.categories:
            by_category[c].append(e)
        for lang in e.languages:
            by_language[lang].append(e)

    write_playlist(out / "index.m3u", entries)
    for group, folder in ((by_country, "countries"), (by_category, "categories"), (by_language, "languages")):
        for key, items in group.items():
            write_playlist(out / folder / f"{key}.m3u", items)

    def channel_names(items: list[Entry]) -> list[dict]:
        unique = {}
        for e in items:
            unique.setdefault(e.channel.id, {"name": e.channel.name, "categories": list(e.channel.categories)})
        return sorted(unique.values(), key=lambda c: c["name"].lower())

    index = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "streams": len(entries),
        "channels": len({e.channel.id for e in entries}),
        "sources": {src: sum(e.stream.source == src for e in entries) for src in sorted({e.stream.source for e in entries})},
        "countries": sorted(
            ({"code": k, "streams": len(v), "channels": channel_names(v)} for k, v in by_country.items()),
            key=lambda c: c["code"],
        ),
        "categories": sorted(
            ({"id": k, "streams": len(v), "channels": len({e.channel.id for e in v})} for k, v in by_category.items()),
            key=lambda c: c["id"],
        ),
        "languages": sorted(
            (
                {"code": k, "name": language_names.get(k, k), "streams": len(v), "channels": len({e.channel.id for e in v})}
                for k, v in by_language.items()
            ),
            key=lambda c: -c["channels"],
        ),
    }
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="iptv-org/database data/ directory")
    parser.add_argument("--streams", type=Path, required=True, help="iptv-org/iptv streams/ directory")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sources", type=Path, help="sources.yml with additional playlists")
    parser.add_argument("--probe", action="store_true", help="drop streams whose first media segment cannot be fetched")
    args = parser.parse_args()
    index = build(args.data, args.streams, args.out, args.probe, args.sources)
    print(f"{index['channels']} channels, {index['streams']} streams, {len(index['countries'])} countries")


if __name__ == "__main__":
    main()
