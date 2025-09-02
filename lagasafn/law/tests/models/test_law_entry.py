"""Tests for LawEntry model."""

import unittest
from lagasafn.law.models.law_entry import LawEntry


class TestLawEntry(unittest.TestCase):
    """Test LawEntry Pydantic model."""
    
    def test_law_entry_creation(self):
        """Test creating a LawEntry with valid data."""
        entry = LawEntry(
            codex_version="155a",
            identifier="6/2025",
            name="Test Law",
            chapter_count=5,
            art_count=20,
            nr=6,
            year=2025,
            problems={"content": {"success": 0.95}}
        )
        
        self.assertEqual(entry.identifier, "6/2025")
        self.assertEqual(entry.name, "Test Law")
        self.assertEqual(entry.nr, 6)
        self.assertEqual(entry.year, 2025)
        self.assertEqual(entry.content_success(), 0.95)
    
    def test_display_content_success(self):
        """Test content success display formatting."""
        entry = LawEntry(
            nr=6,
            year=2025,
            problems={"content": {"success": 0.9567}}
        )
        
        # Should format as percentage with 2 decimal places
        self.assertEqual(entry.display_content_success(), "95.67%")
    
    def test_display_content_success_unknown(self):
        """Test content success display when no content problems."""
        entry = LawEntry(nr=6, year=2025, problems={})
        self.assertEqual(entry.display_content_success(), "unknown")
    
    def test_original_url(self):
        """Test original URL generation."""
        entry = LawEntry(nr=6, year=2025)
        url = entry.original_url()
        self.assertIn("2025006.html", url)
        self.assertIn("althingi.is", url)
    
    def test_str_representation(self):
        """Test string representation."""
        entry = LawEntry(identifier="6/2025")
        self.assertEqual(str(entry), "6/2025")


if __name__ == '__main__':
    unittest.main()