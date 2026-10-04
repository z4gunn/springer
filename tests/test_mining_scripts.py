"""The discovery mining scripts behind spgr-mine-ugc-forums,
spgr-mine-app-store-reviews, and spgr-mine-social-media. Each one hits a free
public endpoint live, so the tests run them against saved fixtures through
--fixture and never touch the network. They assert the shared item shape and
the exit codes the skills key on: 0 items, 1 partial, 2 nothing."""

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

SKILLS = REPO / ".claude" / "skills"
hn = load_script(SKILLS / "spgr-mine-ugc-forums" / "scripts" / "hn_search.py")
apple = load_script(SKILLS / "spgr-mine-app-store-reviews" / "scripts" / "apple_reviews.py")
bsky = load_script(SKILLS / "spgr-mine-social-media" / "scripts" / "bsky_search.py")
GPLAY = SKILLS / "spgr-mine-app-store-reviews" / "scripts" / "google_play_reviews.mjs"

HN_FIXTURE = {
    "nbPages": 1,
    "hits": [
        {"objectID": "9340320", "created_at": "2015-04-08T12:40:51Z", "author": "ben1040",
         "points": None, "num_comments": None, "story_id": 9338480,
         "story_title": "Uber's popularity surges", "title": None, "url": None,
         "comment_text": "Uber now forwards receipts to Concur.<p>It&#x27;s way easier.", "parent_id": 9339568},
        {"objectID": "29421220", "created_at": "2021-12-02T19:30:19Z", "author": "pg",
         "points": 3, "num_comments": 0, "story_id": None, "story_title": None,
         "title": "Expense Reporting Sucks", "url": "https://example.com/post", "comment_text": None,
         "story_text": None},
    ],
}

APPLE_RSS_FIXTURE = {"feed": {"entry": [
    {"author": {"name": {"label": "Reviewer One"}}, "updated": {"label": "2026-10-03T11:09:44-07:00"},
     "im:rating": {"label": "1"}, "im:version": {"label": "26.38.74"}, "id": {"label": "14623759511"},
     "title": {"label": "Locked out"}, "content": {"label": "Cannot access my account."},
     "link": {"attributes": {"rel": "related", "href": "https://itunes.apple.com/us/review?id=310633997&type=Purple%20Software"}},
     "im:voteSum": {"label": "2"}, "im:voteCount": {"label": "3"}},
]}}

APPLE_CATALOG_FIXTURE = {"next": "/v1/catalog/us/apps/310633997/reviews?offset=2", "data": [
    {"id": "14622591346", "type": "user-reviews", "attributes": {
        "date": "2026-10-03T12:26:58Z", "isEdited": False, "rating": 5,
        "review": "Only a human can give a true five star rating.", "title": "What is up", "userName": "J M"}},
]}

BSKY_FIXTURE = {"posts": [
    {"uri": "at://did:plc:abc/app.bsky.feed.post/3kh43lky4s72i",
     "author": {"handle": "yoyoel.com", "displayName": "Yoel Roth"},
     "record": {"text": "Corporate expense reporting: endless.", "createdAt": "2023-12-22T02:58:12.781Z"},
     "likeCount": 92, "replyCount": 4, "repostCount": 4, "quoteCount": 1, "indexedAt": "2023-12-22T02:58:12.781Z"},
], "cursor": "25", "hitsTotal": 1}

GPLAY_FIXTURE = [
    {"id": "e38ae790", "userName": "A User", "date": "2026-10-03T22:22:16.923Z", "score": 5,
     "scoreText": "5", "url": "https://play.google.com/store/apps/details?id=com.whatsapp&reviewId=e38ae790",
     "title": None, "text": "Works well.", "replyDate": None, "replyText": None, "version": "2.26.1",
     "thumbsUp": 7},
]

SHAPE = {"url", "date", "author", "title", "text", "engagement"}


def run_main(module, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = module.main(["script", *argv])
    return rc, json.loads(buf.getvalue())


class MiningScriptsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self, name, obj):
        path = self.dir / name
        path.write_text(json.dumps(obj))
        return str(path)

    def assert_shape(self, result, source):
        self.assertEqual(result["source"], source)
        for key in ("query", "retrieved_at", "items", "errors"):
            self.assertIn(key, result)
        for item in result["items"]:
            self.assertTrue(SHAPE <= set(item), item.keys())
            self.assertTrue(item["url"].startswith("https://"))

    def test_hn_comments_and_stories_map_to_permalinks(self):
        rc, out = run_main(hn, ["expense reporting", "--fixture", self.fixture("hn.json", HN_FIXTURE)])
        self.assertEqual(rc, 0)
        self.assert_shape(out, "hackernews")
        comment, story = out["items"]
        self.assertEqual(comment["url"], "https://news.ycombinator.com/item?id=9340320")
        self.assertEqual(comment["kind"], "comment")
        self.assertEqual(comment["text"], "Uber now forwards receipts to Concur.\n\nIt's way easier.")
        self.assertEqual(comment["title"], "Uber's popularity surges")
        self.assertEqual(story["engagement"], {"points": 3, "num_comments": 0})
        self.assertEqual(story["external_url"], "https://example.com/post")

    def test_hn_limit_and_empty_fixture_exit_codes(self):
        rc, out = run_main(hn, ["q", "--limit", "1", "--fixture", self.fixture("hn.json", HN_FIXTURE)])
        self.assertEqual(rc, 0)
        self.assertEqual(len(out["items"]), 1)
        rc, out = run_main(hn, ["q", "--fixture", self.fixture("empty.json", {"hits": [], "nbPages": 0})])
        self.assertEqual(rc, 2)
        self.assertEqual(out["items"], [])

    def test_hn_since_filter_becomes_a_numeric_filter(self):
        url = hn.build_url("q", "comment", "2025-01-01", 0)
        self.assertIn("numericFilters=created_at_i%3E1735689600", url)
        self.assertIn("tags=comment", url)

    def test_apple_rss_fixture_carries_version_and_votes(self):
        rc, out = run_main(apple, ["310633997", "--fixture", self.fixture("rss.json", APPLE_RSS_FIXTURE)])
        self.assertEqual(rc, 0)
        self.assert_shape(out, "apple-app-store")
        item = out["items"][0]
        self.assertEqual(item["endpoint"], "rss")
        self.assertEqual(item["engagement"], {"rating": 1, "version": "26.38.74", "vote_sum": 2, "vote_count": 3})
        self.assertEqual(item["review_id"], "14623759511")
        self.assertEqual(out["rss_cap"], 500)

    def test_apple_catalog_fixture_is_detected_by_shape(self):
        rc, out = run_main(apple, ["310633997", "--country", "gb",
                                   "--fixture", self.fixture("cat.json", APPLE_CATALOG_FIXTURE)])
        self.assertEqual(rc, 0)
        item = out["items"][0]
        self.assertEqual(item["endpoint"], "catalog")
        self.assertEqual(item["engagement"]["rating"], 5)
        self.assertIn("/gb/app/id310633997", item["url"])

    def test_apple_empty_feed_exits_two(self):
        rc, out = run_main(apple, ["1", "--fixture", self.fixture("none.json", {"feed": {}})])
        self.assertEqual(rc, 2)

    def test_bsky_builds_post_urls_and_engagement(self):
        rc, out = run_main(bsky, ["expense reporting", "--fixture", self.fixture("b.json", BSKY_FIXTURE)])
        self.assertEqual(rc, 0)
        self.assert_shape(out, "bluesky")
        item = out["items"][0]
        self.assertEqual(item["url"], "https://bsky.app/profile/yoyoel.com/post/3kh43lky4s72i")
        self.assertEqual(item["engagement"], {"likes": 92, "replies": 4, "reposts": 4, "quotes": 1})
        self.assertEqual(out["notes"], [])

    def test_bsky_limit_over_the_public_cap_is_a_note_not_an_error(self):
        rc, out = run_main(bsky, ["q", "--limit", "250", "--fixture", self.fixture("b.json", BSKY_FIXTURE)])
        self.assertEqual(rc, 0)
        self.assertEqual(out["errors"], [])
        self.assertEqual(len(out["notes"]), 1)
        self.assertIn("limit=100", bsky.build_url("q", "top", None, 250))
        self.assertIn("since=2025-01-01T00%3A00%3A00Z", bsky.build_url("q", "top", "2025-01-01", 10))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_google_play_fixture_under_node(self):
        proc = subprocess.run(["node", str(GPLAY), "com.whatsapp", "--fixture",
                               self.fixture("gp.json", GPLAY_FIXTURE)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assert_shape(out, "google-play")
        item = out["items"][0]
        self.assertEqual(item["engagement"]["rating"], 5)
        self.assertEqual(item["engagement"]["thumbs_up"], 7)
        self.assertEqual(item["engagement"]["version"], "2.26.1")
        self.assertIn("reviewId=e38ae790", item["url"])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_google_play_missing_app_id_exits_two(self):
        proc = subprocess.run(["node", str(GPLAY)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("app id is required", json.loads(proc.stdout)["errors"][0])


if __name__ == "__main__":
    unittest.main()
