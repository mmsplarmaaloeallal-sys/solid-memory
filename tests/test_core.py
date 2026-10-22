import tempfile
import unittest
from pathlib import Path

from solid_memory.core import EpistemicType, SolidMemory


class SolidMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SolidMemory(Path(self.tmp.name) / "memory.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_search_and_persistence(self):
        entry = self.store.add("The test engine stores evidence.", "CLAIM", 0.7, {"source": "test"})
        self.assertEqual(self.store.get(entry.id).content, entry.content)
        self.assertEqual(len(self.store.search("stores evidence")), 1)
        reopened = SolidMemory(Path(self.tmp.name) / "memory.sqlite3")
        self.assertEqual(reopened.get(entry.id).content_hash, entry.content_hash)

    def test_revision_preserves_parent(self):
        original = self.store.add("First version", "CLAIM")
        revised = self.store.revise(original.id, "Second version")
        self.assertEqual(revised.parent_id, original.id)
        self.assertEqual(self.store.get(original.id).content, "First version")
        self.assertEqual(revised.version, 2)

    def test_invalid_confidence_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add("Bad confidence", confidence=1.5)

    def test_hash_chain_verifies(self):
        self.store.add("A durable memory", EpistemicType.CLAIM)
        report = self.store.verify()
        self.assertTrue(report["ok"], report["issues"])
        self.assertGreaterEqual(report["events_checked"], 2)

    def test_empty_search(self):
        self.assertEqual(self.store.search("   "), [])


if __name__ == "__main__":
    unittest.main()
