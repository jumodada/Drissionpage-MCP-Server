#!/usr/bin/env python3
"""
Basic Navigation Test Scenario

Test basic web navigation functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def test_basic_navigation():
    """Test basic navigation functions."""
    print("🌐 Testing Basic Navigation")
    print("=" * 40)
    
    # This would be the actual test commands you'd use with Claude Code:
    test_commands = [
        "Navigate to https://httpbin.org/html",
        "Take a screenshot of the page", 
        "Get the page title",
        "Go back in history",
        "Go forward in history",
        "Refresh the page"
    ]
    
    print("📝 Test Commands to use with Claude Code:")
    for i, command in enumerate(test_commands, 1):
        print(f"  {i}. {command}")
    
    print("\n💡 Expected Results:")
    print("  • Page should load successfully")
    print("  • Screenshot should be captured")
    print("  • Page title should be extracted")
    print("  • Navigation history should work")
    
    # For local testing without Claude, you can use:
    print("\n🧪 Local Testing (without Claude):")
    print("  python playground/local_test.py")
    

if __name__ == "__main__":
    asyncio.run(test_basic_navigation())