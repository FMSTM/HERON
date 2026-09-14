"""robots.txt.

Положенный руками, он через полгода начинает врать: на старом сайте это уже
произошло — sitemap генерировал заброшенный плагин и отдавал битые адреса,
а robots продолжал на него указывать. Поэтому файл собирается, а не лежит.

Спецификация: docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

from heron.contracts.site import SiteConfig
from heron.core.environment import BuildEnv
from heron.core.urls import absolute


def generate(config: SiteConfig, env: BuildEnv | None = None) -> dict[str, str]:
    env = env or BuildEnv()
    if not env.indexable:
        # Закрытая сборка. Ни sitemap, ни дополнений: любая лишняя строка тут —
        # приглашение краулеру заглянуть, а сборка не предназначена для сети.
        return {"robots.txt": "User-agent: *\nDisallow: /\n"}

    lines = ["User-agent: *", "Allow: /"]
    lines.extend(config.seo.robots_extra)
    lines.append("")
    lines.append(f"Sitemap: {absolute(config, '/sitemap.xml')}")
    return {"robots.txt": "\n".join(lines) + "\n"}
