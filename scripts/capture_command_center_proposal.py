"""Render the isolated synthetic proposal; no server or external access required."""
import json
from html import escape
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

VIEWS = {
    'home': ['Overview', 'My Actions', 'Recent Activity'],
    'jobs': ['Best Matches', 'Shortlisted', 'All Jobs', 'Needs Verification'],
    'applications': ['Priority Queue', 'Preparing', 'Ready to Review', 'Applied', 'Follow-ups'],
    'inbox': ['Recruiter Inbox', 'Job Alerts', 'Draft Approvals', 'Draft History'],
    'sources': ['Source Health', 'Run History', 'Schedules', 'Verification Backlog'],
    'profile': ['Career Facts', 'Documents', 'Saved Answers', 'Preferences'],
}
MAIN = dict(home='Overview', jobs='Best Matches', applications='Preparing', inbox='Recruiter Inbox', sources='Source Health', profile='Career Facts')


def main():
    target = Path('artifacts/command-center-proposal')
    target.mkdir(parents=True, exist_ok=True)
    source = Path('docs/prototypes/command-center.html').resolve().as_uri()
    rows, errors, blocked = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        page.route('http://**/*', lambda r: (blocked.append(r.request.method), r.abort()))
        page.route('https://**/*', lambda r: (blocked.append(r.request.method), r.abort()))
        page.on('pageerror', lambda e: errors.append(str(e)))
        for width in [1440, 768, 390]:
            page.set_viewport_size({'width': width, 'height': 1000})
            for root, views in VIEWS.items():
                for view in views:
                    slug = view.lower().replace(' ', '-')
                    page.goto(f'{source}#{root}/{slug}')
                    expect(page.locator('.subnav [aria-current=page]')).to_have_text(view + {'Preparing': '5', 'Ready to Review': '2', 'Recruiter Inbox': '3', 'Needs Verification': '18', 'My Actions': '3', 'Draft Approvals': '2'}.get(view, ''))
                    page.evaluate('() => document.activeElement.blur()')
                    filename = f'{root}-{slug}-{width}.png'
                    page.screenshot(path=str(target / filename), full_page=True)
                    geometry = page.evaluate('''() => ({overflow:document.documentElement.scrollWidth>innerWidth,
                        sidebar:document.querySelector('.sidebar').getBoundingClientRect().width,
                        header:document.querySelector('.header').getBoundingClientRect().height,
                        padding:parseFloat(getComputedStyle(document.querySelector('main')).paddingLeft),
                        horizontalClip:[...document.querySelectorAll('h1,h2,h3,button')].filter(e=>{
                            const r=e.getBoundingClientRect();return r.width&&r.x>=0&&r.right>innerWidth+1&&!e.closest('.subnav,.table-wrap');}).length})''')
                    rows.append({'workspace': root, 'view': view, 'width': width, 'file': filename, 'representative': MAIN[root] == view, **geometry})
                    assert geometry['header'] == 64
                    assert geometry['sidebar'] == (232 if width == 1440 else 72 if width == 768 else 0)
                    assert geometry['padding'] == (24 if width == 1440 else 20 if width == 768 else 16)
            # Modal viewport/focus and mobile navigation checks use only the prototype.
            page.locator('#notifications').click()
            expect(page.get_by_role('dialog')).to_be_visible()
            box = page.get_by_role('dialog').bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= width
            assert box['y'] >= 0 and box['y'] + box['height'] <= 1000
            page.screenshot(path=str(target / f'notification-dialog-{width}.png'))
            page.keyboard.press('Escape')
            expect(page.get_by_role('dialog')).not_to_be_visible()
            expect(page.locator('#notifications')).to_be_focused()
            if width == 390:
                page.get_by_role('button', name='Open navigation').click()
                expect(page.locator('.sidebar')).to_be_visible()
                page.screenshot(path=str(target / 'mobile-navigation-390.png'))
                page.keyboard.press('Escape')
                expect(page.get_by_role('button', name='Open navigation')).to_be_focused()
            if width == 1440:
                page.get_by_role('button', name='Collapse sidebar').click()
                assert page.locator('.sidebar').bounding_box()['width'] == 72
                page.screenshot(path=str(target / 'collapsed-sidebar-1440.png'))
                page.get_by_role('button', name='Expand sidebar').click()
        # Compact batch keeps technical inventory behind deliberate disclosure.
        page.goto(source + '#applications/preparing')
        assert page.locator('.application').count() == 5
        assert page.locator('.field-details[open]').count() == 0
        page.locator('.field-details summary').first.click()
        expect(page.locator('.field-details').first).to_contain_text('NEEDS INSPECTION')
        page.screenshot(path=str(target / 'application-expanded-390.png'), full_page=True)
        page.goto(source + '#jobs/needs-verification')
        expect(page.locator('[data-role="2"]')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#role-detail')).to_contain_text('Unresolved · not eligible yet')
        page.locator('[data-role="3"]').click()
        expect(page.locator('#role-detail h2')).to_have_text('UI Engineering Lead')
        page.goto(source + '#inbox/recruiter-inbox')
        page.locator('[data-conversation="1"]').click()
        expect(page.locator('#conversation-detail h2')).to_have_text(messages_title := 'A few questions about your frontend experience')
        browser.close()
    report = {'screenshots': rows, 'page_errors': errors, 'network_attempts_blocked': blocked,
              'checks': {'modal_bounds_and_focus': True, 'mobile_menu_escape_focus': True, 'compact_five_card_batch': True}}
    (target / 'index.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    names = dict(home='Home', jobs='Find Jobs', applications='Applications', inbox='Inbox & Drafts', sources='Sources & Activity', profile='My Profile')
    cards = []
    for root, name in names.items():
        slug = MAIN[root].lower().replace(' ', '-')
        links = ''.join(f'<li>{escape(view)}: ' + ' · '.join(f'<a href="{root}-{view.lower().replace(" ", "-")}-{width}.png">{width}px</a>' for width in [1440, 768, 390]) + '</li>' for view in VIEWS[root])
        cards.append(f'<section><h2>{escape(name)}</h2><p><a href="../../docs/prototypes/command-center.html#{root}/{slug}">Open interactive proposal</a></p><a class="screen-link" href="{root}-{slug}-1440.png"><img alt="{escape(name)} proposal" data-base="{root}-{slug}" src="{root}-{slug}-1440.png"></a><details><summary>All subviews and widths</summary><ul>{links}</ul></details></section>')
    gallery = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Command Center · Six-workspace design review</title><style>body{font:14px/1.6 'Segoe UI',sans-serif;color:#233d4a;background:#f4f6f8;margin:0;padding:32px}main{max-width:1440px;margin:auto}h1{font-size:28px;margin:0}h2{font-size:20px}a{color:#17654d}nav{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0;position:sticky;top:0;background:#f4f6f8;padding:12px 0;z-index:1}button{padding:10px 18px;border:1px solid #becdc7;border-radius:7px;background:white;cursor:pointer}button[aria-pressed=true]{background:#17654d;color:white}section{background:white;border:1px solid #dce3e8;border-radius:12px;padding:20px;margin-bottom:24px}img{display:block;width:100%;height:auto;border:1px solid #e2e8ed;border-radius:7px}body.mobile img{max-width:390px;margin:auto}body.tablet img{max-width:768px;margin:auto}details{padding-top:20px}summary{cursor:pointer;font-weight:600}.note{padding:16px;background:#fff6e6;border:1px solid #ebdbb7;border-radius:8px}.extras{display:flex;gap:16px;flex-wrap:wrap}</style><main><h1>Command Center · Proposed visual baseline</h1><p>Review all six workspaces before production implementation.</p><p class="note"><strong>Awaiting explicit design approval.</strong> All data is synthetic. R3 functional verification remains passed; visual acceptance is NOT COMPLETE. These are proposed screens, not the running dashboard.</p><p><a href="../../docs/command-center-design-contract.md">Design contract</a> · <a href="../../docs/prototypes/command-center.html">Interactive prototype</a> · <a href="index.json">72-screen index and geometry checks</a></p><nav aria-label="Screenshot viewport"><button data-width="1440" aria-pressed="true">Desktop · 1440px</button><button data-width="768" aria-pressed="false">Tablet · 768px</button><button data-width="390" aria-pressed="false">Mobile · 390px</button></nav>''' + ''.join(cards) + '''<h2>Additional interaction states</h2><p class="extras"><a href="mobile-navigation-390.png">Mobile navigation</a><a href="collapsed-sidebar-1440.png">Collapsed sidebar</a><a href="notification-dialog-390.png">Mobile dialog</a><a href="application-expanded-390.png">Expanded form inspection</a></p><p>Proposal limits: workflow buttons open explanatory dialogs, search is illustrative, and no backend API is called. Final populated production screenshots and full regression follow only after design approval and implementation.</p></main><script>document.querySelectorAll('[data-width]').forEach(b=>b.onclick=()=>{const w=b.dataset.width;document.body.className=w==='390'?'mobile':w==='768'?'tablet':'';document.querySelectorAll('[data-width]').forEach(n=>n.setAttribute('aria-pressed',String(n===b)));document.querySelectorAll('img[data-base]').forEach(n=>{n.src=n.dataset.base+'-'+w+'.png';n.parentElement.href=n.src;});});</script></html>'''
    (target / 'review.html').write_text(gallery, encoding='utf-8')
    assert not errors and not blocked
    assert not any(r['overflow'] or r['horizontalClip'] for r in rows), 'Review geometry failures in index.json'
    print(json.dumps({'subview_screenshots': len(rows), 'supplemental_screenshots': 6, 'page_errors': len(errors), 'overflow': sum(r['overflow'] for r in rows), 'network_attempts': len(blocked)}))


if __name__ == '__main__':
    main()
