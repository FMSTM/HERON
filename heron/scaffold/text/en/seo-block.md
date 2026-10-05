---
# ================= 1. BASICS =================
title: {title}
# ↑ <title> in search results, up to 60 characters. The theme appends the site suffix (seo.title_suffix)
h1: {h1}
# ↑ heading on the page — for someone who has already opened it; not a copy of title
description: {description}
# ↑ meta description, up to 155 characters: what the visitor gets here
# nav_title:                 # short name in menus and breadcrumbs
# slug:                      # address, if it must differ from the file name. The key is the file name
# canonical:                 # leave empty: the engine sets the canonical address itself
# robots:                    # leave empty: indexing is decided by noindex

# ================= 2. SEARCH QUERIES =================
# main:
# additional:
# total: 0
# The engine does not read this group. One intent — one page

# ================= 3. OPEN GRAPH =================
# og_title:                  # empty — title is used
# og_description:            # empty — description is used
# og_image:                  # empty — seo.og_default_image from site.yaml
# og_image_alt:

# ================= 4. TWITTER / X =================
# twitter_title:             # empty — taken from Open Graph
# twitter_description:
# twitter_image:

# ================= 5. SCHEMA.ORG =================
# schema:                    # markup refinements for this page, on top of site.yaml

# ================= 6. CARD AND CATALOG =================
# image:                     # preview in catalogs: a path in media/
# image_alt:                 # required if image is set
order: {order}
# ↑ order in catalogs and menus, ascending
{type_line}
# ================= 7. SERVICE =================
# date:                      # publication date, YYYY-MM-DD
# updated:                   # last edit date; without it — build.updated_from from site.yaml
published: true
# ↑ false — the page is not built
# noindex: true              # hide from search engines and drop from the sitemap

# ================= 8. RELATIONS =================
# redirect_from:             # old addresses that should 301 here
#   - /old-address/
---
