**English** · [简体中文](README.zh-CN.md) · [Bahasa Melayu](README.ms.md) · [Bahasa Indonesia](README.id.md) · [Tiếng Việt](README.vi.md) · [ไทย](README.th.md)

# Doubo Public Channel Directory

A daily-updated M3U index of TV channels that broadcasters make **freely and publicly available** worldwide. Browse it in your language at <https://doubo.tv/en/playlists/>

> This repository stores and relays **no video**. It only lists links that pass the [inclusion policy](POLICY.md).

## Usage

Paste any of these links into [Doubo](https://doubo.tv) or any player that supports M3U playlists:

| Playlist | URL |
| --- | --- |
| All channels | `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/index.m3u` |
| By country | `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/countries/<code>.m3u` (e.g. `my`, `id`, `vn`, `th`) |
| By category | `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/categories/<id>.m3u` (e.g. `news`, `kids`, `sports`) |
| By language | `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/languages/<code>.m3u` (ISO 639-3, e.g. `msa`, `ind`, `vie`) |
| Machine-readable index | `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/index.json` |
| Programme guide (XMLTV) | `https://doubo.tv/epg/doubo.xml.gz` (already named in every playlist's `x-tvg-url` header; covers the channels with a public guide, about 800) |

### Popular countries

- Malaysia: `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/countries/my.m3u`
- Indonesia: `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/countries/id.m3u`
- Vietnam: `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/countries/vn.m3u`
- Thailand: `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/countries/th.m3u`
- Philippines: `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/countries/ph.m3u`
- Singapore: `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist/countries/sg.m3u`

Mirror: if jsDelivr is slow or blocked on your network, replace `https://cdn.jsdelivr.net/gh/streamline-iptv/iptv-playlists@dist` with `https://raw.githubusercontent.com/streamline-iptv/iptv-playlists/dist`. jsDelivr can lag a few hours behind the daily build; the GitHub link is never more than a few minutes old.

## What gets listed

1. Only streams served from the channel's own website domain, or from a broadcast-grade CDN / official free streaming platform on the [allowlist](policy/allowed-hosts.txt).
2. No paid channels, no adult content, no closed channels.
3. Channels on the iptv-org blocklist or our [takedown list](policy/takedown.csv) are excluded.
4. Every daily build follows each stream to its first video segment and keeps only the ones that play; streams marked geo-blocked are kept because they can only be checked from their own country.

Full details: [POLICY.md](POLICY.md).

## Sources

Channel data and links come from the community projects [iptv-org/database](https://github.com/iptv-org/database) and [iptv-org/iptv](https://github.com/iptv-org/iptv), filtered by the stricter policy above. Other curated public lists are merged too (see [sources.yml](sources.yml)), and a weekly job searches GitHub for public playlists: streams served from a channel’s own website domain are added automatically, while streams on shared CDNs are only listed in [discovered/REPORT.md](discovered/REPORT.md) for review.

## Takedown

Rights holders can ask for a channel or link to be removed with a [takedown request](https://github.com/streamline-iptv/iptv-playlists/issues/new?template=takedown.yml). Requests are handled within 72 hours and take effect in the next daily build.

## Repository layout

- `main`: the generator (`scripts/build.py`), the policy (`policy/`) and the workflow.
- `dist`: the playlists generated every day by GitHub Actions. Do not edit it by hand.

## Contributing

Suggestions for the host allowlist are welcome as pull requests; please explain why the host is an official source. Channel data corrections belong upstream in [iptv-org/database](https://github.com/iptv-org/database).

## License

Code: [MIT](LICENSE). Playlists and index data: [CC BY 4.0](LICENSE-DATA.md); please credit “Doubo Public Channel Directory” when you republish or build on the list. The license covers our selection of links only; every stream belongs to its broadcaster.
