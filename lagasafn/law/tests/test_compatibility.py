"""Tests for backward compatibility layer."""

import unittest
from unittest.mock import patch, MagicMock
from lagasafn.law.compatibility import Law, LawManager


class TestCompatibilityLayer(unittest.TestCase):
    """Test that the compatibility layer maintains the old API."""
    
    @patch('lagasafn.law.compatibility.LawDocumentFactory')
    def test_law_initialization(self, mock_factory):
        """Test that Law class can be initialized like before."""
        # Mock the factory to return a law document
        mock_law_doc = MagicMock()
        mock_law_doc.identifier = "6/2025"
        mock_law_doc.codex_version = "155a"
        mock_law_doc.nr = 6
        mock_law_doc.year = 2025
        mock_law_doc.name = "Test Law"
        
        mock_factory.from_identifier.return_value = mock_law_doc
        
        # Test old-style initialization
        law = Law("6/2025", "155a")
        
        # Verify factory was called correctly
        mock_factory.from_identifier.assert_called_once_with("6/2025", "155a")
        
        # Test property access works like before
        self.assertEqual(law.identifier, "6/2025")
        self.assertEqual(law.codex_version, "155a")
        self.assertEqual(law.nr, "6")  # Note: compatibility layer returns string
        self.assertEqual(law.year, 2025)
    
    @patch('lagasafn.law.compatibility.LawIndexService')
    def test_law_manager_methods(self, mock_service):
        """Test that LawManager methods delegate correctly."""
        # Mock service responses
        mock_index = MagicMock()
        mock_service.get_index.return_value = mock_index
        mock_service.get_codex_versions.return_value = ["154a", "155a"]
        
        # Test delegation
        result_index = LawManager.index("155a")
        result_versions = LawManager.codex_versions()
        
        # Verify service methods were called
        mock_service.get_index.assert_called_once_with("155a")
        mock_service.get_codex_versions.assert_called_once()
        
        # Verify results
        self.assertEqual(result_index, mock_index)
        self.assertEqual(result_versions, ["154a", "155a"])


if __name__ == '__main__':
    unittest.main()