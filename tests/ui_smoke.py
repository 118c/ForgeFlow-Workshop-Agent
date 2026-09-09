"""本地全链路浏览器冒烟测试；由 webapp-testing/with_server.py 启动服务。"""

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    browser_errors = []
    page.on("console", lambda message: browser_errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:5173", wait_until="networkidle")
    assert "ForgeFlow" in page.title()
    assert page.get_by_text("車間多任務作業規劃").is_visible()
    assert page.locator(".flow-node").count() == 5
    visible_text = page.locator("body").inner_text()
    assert all(word not in visible_text for word in ("演示", "模擬", "模拟", "Mock", "Demo"))

    page.get_by_label("Language").select_option("en-US")
    assert page.get_by_text("Workshop Multi-Task Planning").is_visible()
    page.get_by_label("Language").select_option("zh-TW")

    page.get_by_role("button", name="啟動智慧排程").click()
    page.locator(".result-grid").wait_for(state="visible", timeout=15000)
    page.get_by_text("等待審核", exact=True).wait_for(state="visible")
    assert page.locator(".flow-node.completed").count() == 5
    assert page.locator(".gantt-row").count() == 6

    page.get_by_role("button", name="任務中心").click()
    page.locator(".task-layout").wait_for(state="visible")
    assert page.locator(".table-row:not(.table-header)").count() >= 1
    assert all(word not in page.locator("body").inner_text() for word in ("演示", "模擬", "模拟", "Mock", "Demo"))
    page.screenshot(path=str(ARTIFACTS / "task-center.png"), full_page=True)

    page.get_by_role("button", name="查看追蹤").click()
    page.locator(".trace-layout").wait_for(state="visible")
    assert page.locator(".trace-step").count() == 5
    trace_text = page.locator("body").inner_text()
    assert all(word not in trace_text for word in ("演示", "模擬", "模拟", "Mock", "Demo", "deterministic-demo"))
    assert all(
        internal_name not in trace_text
        for internal_name in (
            "device_resource",
            "shift_query",
            "station_assign",
            "plan_generate",
            "human_review",
            "shift_count",
            "generated_by",
            "review_required",
        )
    )
    page.screenshot(path=str(ARTIFACTS / "trace-center.png"), full_page=True)

    page.get_by_role("button", name="資源台帳").click()
    page.locator(".resource-layout, .error-line").first.wait_for(state="visible")
    assert page.locator(".resource-layout").is_visible(), (
        page.locator(".error-line").inner_text() if page.locator(".error-line").count() else browser_errors
    )
    assert page.locator(".equipment-row:not(.table-head)").count() == 6
    assert page.locator(".shift-card").count() == 2
    assert all(word not in page.locator("body").inner_text() for word in ("演示", "模擬", "模拟", "Mock", "Demo"))
    page.screenshot(path=str(ARTIFACTS / "resource-center.png"), full_page=True)

    page.get_by_role("button", name="版本比較").click()
    page.locator(".decision-panel").wait_for(state="visible")
    assert page.locator(".metric-row").count() == 6
    assert page.locator(".plan-side").count() == 2
    assert all(word not in page.locator("body").inner_text() for word in ("演示", "模擬", "模拟", "Mock", "Demo"))
    page.screenshot(path=str(ARTIFACTS / "plan-compare.png"), full_page=True)

    page.get_by_role("button", name="審核中心").click()
    page.locator(".review-layout").wait_for(state="visible")
    assert all(word not in page.locator("body").inner_text() for word in ("演示", "模擬", "模拟", "Mock", "Demo"))
    page.screenshot(path=str(ARTIFACTS / "review-center.png"), full_page=True)
    page.get_by_role("button", name="核准並下發 →").click()
    page.get_by_text("審核已完成，計畫已送交 MES 介面。", exact=False).wait_for(timeout=10000)

    page.get_by_role("button", name="計畫編排").click()
    page.screenshot(path=str(ARTIFACTS / "forgeflow-demo.png"), full_page=True)
    assert not browser_errors, browser_errors
    print("UI smoke passed: planning, resources, comparison, trace and HITL approval")
    browser.close()
