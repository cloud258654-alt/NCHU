from __future__ import annotations

import asyncio
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import core.runtime_settings as runtime_settings
from playwright.async_api import async_playwright


async def main() -> int:
    state_path = Path(runtime_settings.THREADS_STORAGE_STATE_PATH)
    print(f"Threads Storage State Path is configured as: {state_path}")
    state_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        print("Launching Chromium browser in non-headless mode...")
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("Navigating to Threads login page...")
        await page.goto("https://www.threads.net/login")
        
        print("\n" + "=" * 60)
        print("Please complete the Threads/Instagram login process in the browser window.")
        print("Once you are logged in and see your home feed, press [ENTER] in this terminal...")
        print("=" * 60 + "\n")
        
        # Wait for user input in console
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input)
        
        print(f"Saving login state to: {state_path}")
        await context.storage_state(path=str(state_path))
        print("Successfully saved storage state!")
        
        await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
