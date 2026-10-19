"""Tests for the draft news and fact-check domain allowlist (plan 03-01, OD-3 option A, D-13).

The list is an editorial choice and a disclosed selection bias that the owner reviews at the 03-01
checkpoint. These tests pin its shape: at most 60 entries, one category comment per entry, lowercase
registrable domains, no duplicates, no shortener, and a path resolved from the package location
(never from the working directory).
"""

import importlib.resources
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = REPO_ROOT / "src" / "truthtrail" / "data" / "seed_domains.txt"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from spike_lib import analysis  # noqa: E402
from spike_lib import selection as sel  # noqa: E402

CATEGORIES = {
    "wire-service",
    "public-broadcaster",
    "fact-checker",
    "newspaper-of-record",
    "news-agency",
    "science-news",
}
DOMAIN_RX = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def entries() -> list[tuple[str, str]]:
    """(domain, category) for every non-comment line."""
    rows = []
    for line in SEED_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        domain, _, comment = line.partition("#")
        rows.append((domain.strip(), comment.strip()))
    return rows


def test_the_file_is_read_from_the_package_path():
    resource = importlib.resources.files("truthtrail").joinpath("data", "seed_domains.txt")
    assert Path(str(resource)).resolve() == SEED_FILE.resolve()
    assert SEED_FILE.is_file()


def test_the_tool_default_is_the_package_file_regardless_of_the_working_directory(
    monkeypatch, tmp_path
):
    import importlib.util

    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location(
        "bluesky_spike_seed", REPO_ROOT / "scripts" / "bluesky_spike.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["bluesky_spike_seed"] = module
    spec.loader.exec_module(module)
    assert module.DEFAULT_ALLOWLIST.resolve() == SEED_FILE.resolve()


def test_header_states_that_the_list_is_a_draft_for_the_owner():
    head = "\n".join(SEED_FILE.read_text(encoding="utf-8").splitlines()[:12])
    assert "DRAFT" in head
    assert "OD-3" in head
    assert "03-01" in head


def test_at_most_sixty_entries_and_not_empty():
    rows = entries()
    assert 20 <= len(rows) <= 60


def test_every_entry_has_an_allowed_category_comment():
    for domain, category in entries():
        assert category in CATEGORIES, (domain, category)


def test_entries_are_lowercase_registrable_domains_without_www():
    for domain, _category in entries():
        assert domain == domain.lower(), domain
        assert not domain.startswith("www."), domain
        assert DOMAIN_RX.match(domain), domain
        assert "/" not in domain
        assert ":" not in domain


def test_no_duplicates_and_no_shortener():
    domains = [d for d, _c in entries()]
    assert len(domains) == len(set(domains))
    for domain in domains:
        assert not sel.is_shortener(domain), domain
    assert not any(domain in sel.SHORTENERS for domain in domains)


def test_no_entry_is_a_social_platform_video_site_or_blog_host():
    excluded = {
        "x.com", "twitter.com", "facebook.com", "instagram.com", "youtube.com", "youtu.be",
        "tiktok.com", "reddit.com", "medium.com", "substack.com", "wordpress.com",
        "blogspot.com", "bsky.app", "bsky.social", "tumblr.com", "linkedin.com",
    }  # fmt: skip
    domains = {d for d, _c in entries()}
    assert not domains & excluded


def test_the_loader_returns_the_same_entries():
    loaded = analysis.load_allowlist(SEED_FILE)
    assert loaded == [d for d, _c in entries()]
    assert sel.host_allowed(f"www.{loaded[0]}".removeprefix("www."), loaded)
    assert not sel.host_allowed(f"evil{loaded[0]}", loaded)
    assert not sel.host_allowed(f"{loaded[0]}.evil.example", loaded)
