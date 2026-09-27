"""Build a deterministic, self-contained preview for the offline demo."""

from __future__ import annotations

import html
from typing import Any, Mapping, Sequence


def _text(value: object) -> str:
    return html.escape(str(value), quote=True)


def _paragraphs(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return "".join(f"<p>{_text(line)}</p>" for line in lines)


def build_demo_preview(
    *,
    topic: str,
    title: str,
    hook: str,
    script: str,
    storyboard: Mapping[str, Any],
    platform_files: Mapping[str, str],
    package_id: str,
) -> str:
    """Return portable HTML with no scripts, remote assets, or network URLs."""

    raw_scenes = storyboard.get("scenes", ())
    scenes: Sequence[Mapping[str, Any]] = (
        tuple(item for item in raw_scenes if isinstance(item, Mapping))
        if isinstance(raw_scenes, Sequence) and not isinstance(raw_scenes, (str, bytes))
        else ()
    )
    scene_cards = []
    for index, scene in enumerate(scenes, start=1):
        start = scene.get("start_seconds", 0)
        end = scene.get("end_seconds", 0)
        scene_cards.append(
            "<article class=\"scene\">"
            f"<div class=\"scene-no\">{index:02d}</div>"
            f"<div><span class=\"time\">{_text(start)}-{_text(end)} sec</span>"
            f"<h3>{_text(scene.get('purpose', 'scene'))}</h3>"
            f"<p>{_text(scene.get('visual_prompt', ''))}</p></div>"
            "</article>"
        )
    platform_links = "".join(
        f"<li><code>{_text(platform)}</code><span>{_text(filename)}</span></li>"
        for platform, filename in sorted(platform_files.items())
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(title)} | AI Content Factory demo</title>
  <style>
    :root {{ color-scheme: light; --ink:#17202a; --muted:#5e6b75; --paper:#f5f7f8; --line:#d8dee3; --blue:#176b87; --green:#19734b; --orange:#d46a1f; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
    main {{ width:min(1080px,calc(100% - 32px)); margin:0 auto; padding:40px 0 64px; }}
    header {{ border-top:5px solid var(--blue); padding:34px 0 28px; border-bottom:1px solid var(--line); }}
    .eyebrow {{ margin:0 0 12px; color:var(--blue); font-weight:750; text-transform:uppercase; letter-spacing:.08em; font-size:12px; }}
    h1 {{ max-width:820px; margin:0; font-size:clamp(34px,6vw,64px); line-height:1.02; letter-spacing:0; }}
    .hook {{ max-width:760px; margin:20px 0 0; color:var(--muted); font-size:21px; }}
    .status {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:24px; }}
    .status span {{ border:1px solid var(--line); background:white; padding:7px 10px; border-radius:4px; font-size:13px; }}
    .status strong {{ color:var(--green); }}
    section {{ padding:30px 0; border-bottom:1px solid var(--line); }}
    h2 {{ margin:0 0 18px; font-size:24px; }}
    .script {{ max-width:800px; padding-left:18px; border-left:4px solid var(--orange); }}
    .script p {{ margin:0; font-size:18px; }}
    .scenes {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:12px; }}
    .scene {{ min-height:190px; background:white; border:1px solid var(--line); border-radius:6px; padding:18px; display:grid; grid-template-columns:42px 1fr; gap:10px; }}
    .scene-no {{ font-weight:800; color:var(--orange); font-size:22px; }}
    .scene h3 {{ margin:6px 0; font-size:18px; text-transform:capitalize; }}
    .scene p {{ margin:0; color:var(--muted); font-size:14px; }}
    .time {{ color:var(--blue); font-size:12px; font-weight:700; }}
    ul {{ list-style:none; padding:0; margin:0; display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:8px; }}
    li {{ background:white; border:1px solid var(--line); border-radius:4px; padding:10px 12px; display:flex; justify-content:space-between; gap:12px; }}
    li span {{ color:var(--muted); font-size:12px; overflow-wrap:anywhere; }}
    footer {{ padding-top:24px; color:var(--muted); font-size:13px; }}
    code {{ color:var(--blue); font-weight:700; }}
  </style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">Offline release-candidate demo</p>
    <h1>{_text(title)}</h1>
    <p class="hook">{_text(hook)}</p>
    <div class="status"><span><strong>Pipeline complete</strong></span><span>Fixture providers</span><span>Network: off</span><span>Remote writes: 0</span></div>
  </header>
  <section><h2>Short script</h2><div class="script">{_paragraphs(script)}</div></section>
  <section><h2>Storyboard</h2><div class="scenes">{''.join(scene_cards)}</div></section>
  <section><h2>Platform-ready package</h2><ul>{platform_links}</ul></section>
  <footer>
    <p><strong>Topic:</strong> {_text(topic)}</p>
    <p><strong>Package ID:</strong> <code>{_text(package_id)}</code></p>
    <p>This preview is deterministic synthetic output. Review factual claims and replace fixture providers before publication.</p>
  </footer>
</main>
</body>
</html>
"""


__all__ = ["build_demo_preview"]
