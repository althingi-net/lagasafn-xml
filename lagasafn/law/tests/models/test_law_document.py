"""Tests for LawDocument model."""

import unittest
from lagasafn.law.models.law_document import LawDocument


class TestLawDocument(unittest.TestCase):
    """Test LawDocument Pydantic model."""
    
    def test_law_document_creation(self):
        """Test creating a LawDocument with required fields."""
        doc = LawDocument(
            identifier="6/2025",
            nr=6,
            year=2025,
            name="Test Law Document"
        )
        
        self.assertEqual(doc.identifier, "6/2025")
        self.assertEqual(doc.nr, 6)
        self.assertEqual(doc.year, 2025)
        self.assertEqual(doc.name, "Test Law Document")
        
        # Default values
        self.assertEqual(doc.superchapters, [])
        self.assertEqual(doc.chapters, [])
        self.assertEqual(doc.articles, [])
        self.assertEqual(doc.references, [])
    
    def test_toc_name_cleaning(self):
        """Test table of contents name cleaning."""
        # Test HTML tag removal and whitespace cleaning
        dirty_name = "<b>Article  Name</b>  with   spaces"
        clean_name = LawDocument.toc_name(dirty_name)
        
        self.assertEqual(clean_name, "Article Name with spaces")
    
    def test_str_representation(self):
        """Test string representation."""
        doc = LawDocument(identifier="6/2025", nr=6, year=2025)
        self.assertEqual(str(doc), "6/2025")
    
    def test_pydantic_validation(self):
        """Test Pydantic field validation."""
        # This should work without issues (the main fix we implemented)
        doc = LawDocument(identifier="6/2025", nr=6, year=2025)
        
        # Test that Pydantic internals are properly initialized
        self.assertTrue(hasattr(doc, '__pydantic_fields_set__'))
        self.assertTrue(hasattr(doc, '__pydantic_extra__'))


if __name__ == '__main__':
    unittest.main()