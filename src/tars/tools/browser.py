from __future__ import annotations

import json
from typing import Any

from tars.tools.base import Tool, ToolResult

MAX_CONTENT = 100_000


class BrowserTool(Tool):
    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Browser automation via Playwright: navigate, screenshot, extract text, "
            "fill forms. Requires playwright to be installed."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "screenshot", "extract", "click", "fill"],
                    "description": "Browser action to perform",
                },
                "url": {"type": "string", "description": "URL to navigate to"},
                "selector": {
                    "type": "string",
                    "description": "CSS selector for click/fill/extract",
                },
                "value": {
                    "type": "string",
                    "description": "Value for fill action",
                },
                "output_path": {
                    "type": "string",
                    "description": "Path for screenshot output",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        url = kwargs.get("url", "")
        selector = kwargs.get("selector", "")
        value = kwargs.get("value", "")
        output_path = kwargs.get("output_path", "screenshot.png")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ToolResult(
                success=False,
                error=(
                    "playwright not installed. Run: "
                    "pip install playwright && playwright install chromium"
                ),
            )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                if action == "navigate":
                    if not url:
                        return ToolResult(success=False, error="URL required for navigate")
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    title = await page.title()
                    content = await page.content()
                    await browser.close()
                    return ToolResult(
                        success=True,
                        output=content[:MAX_CONTENT],
                        data={"title": title, "url": url},
                    )

                if action == "screenshot":
                    if url:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.screenshot(path=output_path, full_page=True)
                    await browser.close()
                    return ToolResult(
                        success=True,
                        output=f"Screenshot saved to {output_path}",
                        data={"path": output_path},
                    )

                if action == "extract":
                    if url:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if selector:
                        elements = await page.query_selector_all(selector)
                        texts = []
                        for el in elements[:100]:
                            text = await el.text_content()
                            if text:
                                texts.append(text.strip())
                        await browser.close()
                        return ToolResult(
                            success=True,
                            output=json.dumps(texts, indent=2),
                            data={"count": len(texts)},
                        )
                    text = await page.text_content("body") or ""
                    await browser.close()
                    return ToolResult(
                        success=True,
                        output=text[:MAX_CONTENT],
                    )

                if action == "click":
                    if not selector:
                        return ToolResult(success=False, error="Selector required for click")
                    if url:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.click(selector, timeout=10000)
                    await browser.close()
                    return ToolResult(success=True, output=f"Clicked: {selector}")

                if action == "fill":
                    if not selector or not value:
                        return ToolResult(
                            success=False, error="Selector and value required for fill"
                        )
                    if url:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.fill(selector, value, timeout=10000)
                    await browser.close()
                    return ToolResult(
                        success=True, output=f"Filled {selector} with value"
                    )

                await browser.close()
                return ToolResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            return ToolResult(success=False, error=f"Browser error: {e}")
