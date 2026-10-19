import {defineConfig} from '@playwright/test';
import original from './playwright.config';
export default defineConfig({
 ...original,
 globalTeardown:'./e2e/privacy-teardown.ts',
 outputDir:'test-results-privacy',
 reporter:[['list'],['html',{outputFolder:'playwright-report-privacy',open:'never'}]],
 use:{...original.use,baseURL:'http://127.0.0.1:8019'},
 webServer:{command:'.\\.venv\\Scripts\\python.exe -m tests.ui_fixture_server',
   url:'http://127.0.0.1:8019/api/health',reuseExistingServer:false,timeout:60_000},
});
