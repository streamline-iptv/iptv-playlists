# 收录规则 · Inclusion policy

本目录只是一个索引：不存储、不转码、不转发任何视频，也不提供任何付费频道的访问方式。每条链接在每日构建时都要通过以下全部规则：

This directory is an index only: it stores, transcodes and relays no video and offers no access to paid channels. Every link must pass all of the rules below at each daily build:

1. **频道可识别** · The channel exists in [iptv-org/database](https://github.com/iptv-org/database) with a country and categories.
2. **非成人、未停播** · The channel is not marked NSFW, is not in the `xxx` category and has not closed.
3. **未被投诉** · The channel is not on the iptv-org blocklist (DMCA / NSFW) and is not on our own [takedown list](policy/takedown.csv).
4. **来源可信** · The stream is served either from one of the channel's own domains (its website's domain, plus other domains its broadcaster runs, listed with evidence in [`policy/official-domains.csv`](policy/official-domains.csv)), or from a host in [`policy/allowed-hosts.txt`](policy/allowed-hosts.txt) (broadcast-grade CDNs, official free ad-supported platforms, public access TV). Links on a redirect service in [`policy/redirectors.txt`](policy/redirectors.txt) are followed at build time; the address they land on is judged by this rule and is what gets listed. If the service refuses a link with 403 because the feed is locked to another region, and the file records which platform that kind of link lands on (for example Pluto TV), the link is kept as it is, labelled geo-blocked, and judged by that platform. Bare IP addresses, unknown relay hosts and the paid-operator and aggregator accounts in [`policy/blocked-hosts.txt`](policy/blocked-hosts.txt) are always left out, even on an allowed CDN.
5. **可以播放** · Each daily build follows the stream to its first media segment (master playlist → variant → segment) and checks that the segment is real audio/video. Streams labelled geo-blocked are kept, because they can only be checked from their own country.

**来源** · Sources: every stream above can come from iptv-org, another curated list in [`sources.yml`](sources.yml), or the weekly discovery job ([`scripts/discover.py`](scripts/discover.py)). Discovery adds a stream automatically only when it is served from one of the channel's own domains; streams found on shared CDNs are listed in [`discovered/REPORT.md`](discovered/REPORT.md) and need a person to review the list and add it to `sources.yml`. All sources go through the same rules.

修改白名单、官方域名表、屏蔽列表或跳转服务列表需提交 Pull Request 并说明理由。Changes to the allowlist, the official-domains list, the blocked-hosts list or the redirector list go through a pull request with a short justification.

## 下架 · Takedown

提交[下架申请](https://github.com/streamline-iptv/iptv-playlists/issues/new?template=takedown.yml)，或在申请中注明频道 ID / 链接。处理后条目会写入 `policy/takedown.csv`，下一次构建即移除。

File a [takedown request](https://github.com/streamline-iptv/iptv-playlists/issues/new?template=takedown.yml) naming the channel ID or link. Once handled, the entry is added to `policy/takedown.csv` and disappears from the next build.
