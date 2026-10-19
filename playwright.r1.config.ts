import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./e2e/r1',outputDir:'test-results-r1',workers:1,retries:0,timeout:120_000,expect:{timeout:20_000},
 reporter:[['list'],['html',{outputFolder:'playwright-report-r1',open:'never'}]],
 use:{baseURL:'http://127.0.0.1:8017',channel:'chrome',trace:'retain-on-failure',screenshot:'only-on-failure'},
 webServer:{command:'.\\.venv\\Scripts\\python.exe -m tests.r1_fixture_server',url:'http://127.0.0.1:8017/api/health',reuseExistingServer:false,timeout:60_000},
});
