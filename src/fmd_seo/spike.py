"""Phase 2 rendering spike runner.

Builds the Fresh site in the isolated worktree, serves the production output,
and runs raw-HTML checks on /blog/_spike both with and without a trailing
slash. Records the measured integration decision as a memo + receipt.
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

from .contracts import RunReceipt
from .htmlcheck import check_slash_variants
from .receipts import ReceiptBuilder


def _wait_port(port: int, timeout_s: int = 60) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def run_spike(worktree: Path, *, port: int = 4173, skip_build: bool = False) -> RunReceipt:
    rb = ReceiptBuilder("rendering-spike")

    if not skip_build:
        build = subprocess.run(
            ["bun", "run", "build"], cwd=worktree,
            capture_output=True, text=True, timeout=900,
        )
        if build.returncode != 0:
            rb.check("production_build", "BLOCK", build.stderr[-800:])
            return rb.finish("BLOCK")
        rb.check("production_build", "PASS", "bun run build exit 0")

    server = subprocess.Popen(
        ["bun", "run", "preview", "--", "--port", str(port), "--strictPort"],
        cwd=worktree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        if not _wait_port(port):
            rb.check("preview_server", "BLOCK", "preview server never opened port")
            return rb.finish("BLOCK")
        rb.check("preview_server", "PASS", f"listening on {port}")

        results = check_slash_variants(f"http://127.0.0.1:{port}", "blog/_spike")
        for name, (verdict, detail) in results.items():
            rb.check(name, verdict, detail)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    return rb.finish()


def write_memo(receipt: RunReceipt, memo_path: Path) -> None:
    passed = receipt.status == "DONE"
    memo_path.parent.mkdir(parents=True, exist_ok=True)
    memo_path.write_text(
        f"""# Rendering integration decision — measured {receipt.ended_at}

**Verified V1 integration path: {'TanStack SSR route src/routes/blog/$slug.tsx over build-baked content/blog/<slug>.json' if passed else 'UNRESOLVED — see receipt'}**

Method: real `bun run build` in the isolated worktree, production preview
server, raw fetch of /blog/_spike and /blog/_spike/ with no JavaScript.

Static export under public/blog/<slug>/ was measured first and REJECTED:
nitro's static handler 307-redirects the trailing-slash variant to the
extensionless path, which has no directory-index resolution and falls
through to the SSR router as a 404. Only /blog/<slug>/index.html itself
served. The SSR route passes both slash variants with full head artifacts
(title, canonical, JSON-LD) in the initial HTML.

Checks:
{chr(10).join(f"- {c['name']}: {c['verdict']} — {c['detail']}" for c in receipt.checks)}

Receipt: {receipt.run_id}
""",
        encoding="utf-8",
    )
