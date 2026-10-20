"""The checkout path is scrubbed before a message is cut.

Same rules as internal/aqv/runner_scrub_test.go. A work folder nested in the checkout is longer, so
it has to be replaced first; otherwise it survives as <repo>/.aqv-out and the cut still depends on
where the tree was checked out.
"""
import os
import tempfile
import unittest

from aqv.runner import parse_junit, path_pairs, scrub_paths


class ScrubPathsTest(unittest.TestCase):
    def test_scrub_before_cut_ignores_checkout_length(self):
        def cut(repo):
            work = repo + "/.aqv-out"
            text = "n" * 250 + " " + work + "/service.log: listen failed; " + repo + "/main.go: exit 1"
            return scrub_paths(text, [(repo, "<repo>"), (work, "<work>")])[-80:]

        short = cut("/c")
        long = cut("/very/long/checkout/that/would/shift/the/cut")
        self.assertEqual(short, long)
        self.assertIn("<work>/service.log: listen failed", short)
        self.assertNotIn("<repo>/.aqv-out", short)

    def test_path_pairs_scrub_link_and_target(self):
        with tempfile.TemporaryDirectory() as root:
            real = os.path.join(root, "real")
            os.mkdir(real)
            link = os.path.join(root, "link")
            os.symlink(real, link)
            abs_link = os.path.abspath(link)
            abs_real = os.path.realpath(abs_link)
            self.assertNotEqual(abs_real, abs_link)
            got = scrub_paths(abs_link + "/a " + abs_real + "/b", path_pairs(link))
            self.assertEqual(got, "<repo>/a <repo>/b")
            self.assertNotIn("<work>", [label for _, label in path_pairs(real)])

    def test_parse_junit_scrubs_paths_before_cutting(self):
        repo = "/var/checkout/" + "p" * 180
        work = repo + "/.aqv-out"
        build = "collection " + repo + "/" + "d" * 220 + " END"
        fail = "got 500 from " + work + "/service.log and " + repo + "/handler.go"
        xml = (
            "<testsuite>\n"
            f'<testcase classname="pkg" name=""><error>{build}</error></testcase>\n'
            f'<testcase classname="pkg" name="TestAC_auth_001_SignIn"><failure>{fail}</failure></testcase>\n'
            "</testsuite>\n"
        )
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "junit.xml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(xml)
            pairs = [(repo, "<repo>"), (work, "<work>")]
            cases, errs = parse_junit([path], pairs)
        want = "pkg: " + scrub_paths(build, pairs)[:200]
        self.assertEqual(errs, [want])
        self.assertNotIn(" END", errs[0])
        self.assertNotIn(repo, errs[0])
        self.assertTrue(errs[0].startswith("pkg: collection <repo>/"))
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].message, "got 500 from <work>/service.log and <repo>/handler.go")


if __name__ == "__main__":
    unittest.main()
