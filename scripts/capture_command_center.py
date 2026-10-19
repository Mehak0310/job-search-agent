"""Private, GET-only responsive evidence. Never follows external links or writes APIs."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

VIEWS = {
    'home-panel': ['Overview', 'My Actions', 'Recent Activity'],
    'opportunities-panel': ['Best Matches', 'Shortlisted', 'All Jobs', 'Needs Verification'],
    'browser-panel': ['Priority Queue', 'Preparing', 'Ready to Review', 'Applied', 'Follow-ups'],
    'email-leads-panel': ['Recruiter Inbox', 'Job Alerts', 'Draft Approvals', 'Draft History'],
    'discovery-panel': ['Source Health', 'Run History', 'Schedules', 'Verification Backlog'],
    'professional-profile': ['Career Facts', 'Documents', 'Saved Answers', 'Preferences'],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['before', 'after'], required=True)
    args = parser.parse_args()
    target = Path('data/ui-redesign') / args.phase
    target.mkdir(parents=True, exist_ok=True)
    results, errors, blocked = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context()

        def guard(route):
            request = route.request
            if request.method != 'GET' or urlsplit(request.url).netloc != '127.0.0.1:8000':
                blocked.append({'method': request.method, 'external': urlsplit(request.url).netloc != '127.0.0.1:8000'})
                route.abort()
            else:
                route.continue_()

        context.route('**/*', guard)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in [1440, 768, 390]:
            page.set_viewport_size({'width': width, 'height': 1000})
            for root, views in VIEWS.items():
                for view in views:
                    slug = view.lower().replace(' ', '-')
                    page.goto(f'http://127.0.0.1:8000/#{root}/{slug}')
                    page.locator('.command-subnav [aria-current=page]').wait_for()
                    expect(page.locator("#command-worker")).not_to_have_text("Checking worker")
                    page.wait_for_timeout(250)
                    path = target / f'{root}-{slug}-{width}.png'
                    page.screenshot(path=str(path), full_page=True)
                    geometry = page.evaluate('''() => ({overflow:document.documentElement.scrollWidth>innerWidth,
                        sidebar:document.querySelector('.command-sidebar').getBoundingClientRect().width,
                        header:document.querySelector('body>header').getBoundingClientRect().height,
                        content:document.querySelector('main').getBoundingClientRect().width})''')
                    results.append({'root': root, 'view': view, 'width': width, 'path': str(path), **geometry})
        browser.close()
    (target / 'index.json').write_text(json.dumps({'screenshots': results, 'page_errors': errors, 'blocked_requests': blocked}, indent=2), encoding='utf-8')
    print(json.dumps({'screenshots': len(results), 'overflow': sum(r['overflow'] for r in results), 'page_errors': len(errors), 'blocked_requests': len(blocked)}))


if __name__ == '__main__':
    main()
