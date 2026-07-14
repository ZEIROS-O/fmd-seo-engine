import http.server
import threading
from functools import partial
from pathlib import Path

import pytest

from fmd_seo.htmlcheck import check_page, check_slash_variants

GOOD_PAGE = """<!DOCTYPE html><html><head><title>Good Page</title>
<link rel="canonical" href="https://x/blog/good/">
<script type="application/ld+json">{"@type":"BlogPosting"}</script>
</head><body><article><h1>Good</h1>
<p>%s</p>
<img src="/img.png" alt="described image">
<a href="/">Home</a>
<p>Book your interior detail today.</p>
</article></body></html>""" % ("substantial body text. " * 30)

BAD_PAGE = """<html><head></head><body><div id="root"></div>
<script src="/app.js"></script></body></html>"""


@pytest.fixture
def site(tmp_path):
    (tmp_path / "blog" / "good").mkdir(parents=True)
    (tmp_path / "blog" / "good" / "index.html").write_text(GOOD_PAGE)
    (tmp_path / "blog" / "bad").mkdir(parents=True)
    (tmp_path / "blog" / "bad" / "index.html").write_text(BAD_PAGE)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_good_page_passes_all_checks(site):
    results = check_slash_variants(site, "blog/good")
    failing = {k: v for k, v in results.items() if v[0] != "PASS"}
    assert failing == {}


def test_spa_shell_blocks_content_checks(site):
    results = check_page(f"{site}/blog/bad/")
    verdicts = {k: v[0] for k, v in results.items()}
    assert verdicts["title"] == "BLOCK"
    assert verdicts["canonical"] == "BLOCK"
    assert verdicts["body_substantial"] == "BLOCK"
    assert verdicts["structured_data"] == "BLOCK"


def test_unreachable_url_blocks_fetch():
    results = check_page("http://127.0.0.1:1/nope/", min_body_chars=1)
    assert results["fetch"][0] == "BLOCK"
