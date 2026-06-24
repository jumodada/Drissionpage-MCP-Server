#!/usr/bin/env python3
"""
Data Extraction Test Scenario

Test data extraction and element finding functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def test_data_extraction():
    """Test data extraction functions."""
    print("📊 Testing Data Extraction") 
    print("=" * 40)
    
    # Test commands for Claude Code
    test_commands = [
        "Navigate to https://httpbin.org/html",
        "Get all text content from the page",
        "Get the HTML content of the h1 element", 
        "Get the text of the first paragraph",
        "Get the href attribute of the first link",
        "Get all text from elements with tag 'p'",
        "Take a screenshot highlighting found elements"
    ]
    
    print("📝 Test Commands to use with Claude Code:")
    for i, command in enumerate(test_commands, 1):
        print(f"  {i}. {command}")
    
    print("\n💡 Expected Results:")
    print("  • Page text should be extracted completely")
    print("  • Specific elements should be found by selector")
    print("  • Attributes should be retrieved correctly")
    print("  • HTML structure should be preserved")
    
    print("\n🎯 Good Test Sites for Data Extraction:")
    print("  • https://httpbin.org/html (Simple HTML)")
    print("  • https://quotes.toscrape.com/ (Quotes to scrape)")
    print("  • https://books.toscrape.com/ (Book catalog)")
    print("  • https://httpbin.org/json (JSON data)")
    
    print("\n🧪 Advanced Selectors to Test:")
    selectors = [
        "h1",                    # Tag selector
        ".quote",               # Class selector  
        "#quote-1",             # ID selector
        "[href]",               # Attribute selector
        "div > p",              # Child selector
        "h1, h2, h3",           # Multiple selector
        ":first-child",         # Pseudo selector
    ]
    
    print("  CSS Selectors:")
    for selector in selectors:
        print(f"    • {selector}")


if __name__ == "__main__":
    asyncio.run(test_data_extraction())