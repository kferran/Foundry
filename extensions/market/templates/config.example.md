---
type: config
market_watch:
  - {name: "Vendor A", group: vendors, newsroom: "https://vendor-a.example.com/news/"}
  - {name: "Vendor B", group: vendors, feed: "https://vendor-b.example.com/feed.xml"}
  - {name: "Partner C", group: partners, newsroom: "https://partner-c.example.org/about/newsroom.html", feed: "https://partner-c.example.org/rss", match: "/"}
  - {name: "Standards Body D", group: standards}
  - {name: "Runtime E", group: engineering, feed: "https://runtime-e.example.com/releases.atom", exclude: "-rc\\d*\\b"}
market_press:
  - {name: "Trade News F", feed: "https://trade-news-f.example.com/rss"}
market_alert_groups: [vendors, partners, standards]
market_keep_groups: []
---
An example of the market extension's keys, with placeholder names and hosts only. Copy the keys into `system/config.md` and replace them with your own groups, entries and press feeds. "Standards Body D" is a name-only entry: it has no newsroom or feed and is matched only through the press feeds.
