---
# ================= 1. BASICS =================
title: "Interior design"
# ↑ <title> in search results, up to 60 characters. The theme appends the site suffix (seo.title_suffix)
h1: "Apartment design, start to finish"
# ↑ heading on the page - for someone who has already opened it; not a copy of title
description: "We plan the space and pick the materials."
# ↑ meta description, up to 155 characters: what the visitor gets here
# nav_title: Design          # short name in menus and breadcrumbs
# slug:                      # address, if it must differ from the file name. The key is the file name;
#                            # in the Russian translation of this page - slug: dizajn
# canonical:                 # leave empty: the engine sets the canonical address itself
# robots:                    # leave empty: indexing is decided by noindex

# ================= 2. SEARCH QUERIES =================
# main: interior design
# additional: apartment design
# total: 2
# The engine does not read this group. One intent - one page

# ================= 3. OPEN GRAPH =================
# og_title:                  # empty - title is used
# og_description:            # empty - description is used
# og_image:                  # empty - seo.og_default_image from site.yaml
# og_image_alt:

# ================= 4. TWITTER / X =================
# twitter_title:             # empty - taken from Open Graph
# twitter_description:
# twitter_image:

# ================= 5. SCHEMA.ORG =================
# schema:                    # markup refinements for this page, on top of site.yaml
#   Service:
#     serviceType: interior design

# ================= 6. CARD AND CATALOG =================
# image: media/services/design.png   # preview in catalogs: a path in media/
# image_alt:                 # required if image is set
order: 10
# ↑ order in catalogs and menus, ascending
# type: service              # type, if the section does not set it (children_type in _index.md)

# ================= 7. SERVICE =================
# date: 2026-03-14           # publication date, YYYY-MM-DD; group 7 is service data, not the service page type
# updated: 2026-09-02        # last edit date; without it - build.updated_from from site.yaml
published: true
# ↑ false - the page is not built
# noindex: true              # hide from search engines and drop from the sitemap

# ================= 8. RELATIONS =================
related:
  - planning
# ↑ relation field from theme.yaml: file names without .md
redirect_from:
  - "/old-address/"
# ↑ old addresses that should 301 here; Cyrillic or %D0%… - either works
---

Intro: who we help and with what.

Promise: what the work ends with.

## What is included {#includes}

- **Measurements.** We measure the rooms.
- **Project.** Drawings and a material list.

## How we work {#how}

1. **Request.** Call or write to us.
2. **Meeting.** We discuss the task.

## FAQ {#faq}

### How long does it take?

Usually two to three weeks.
