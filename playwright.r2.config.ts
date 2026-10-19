import {defineConfig} from '@playwright/test';
export default defineConfig({
 globalTeardown:'./e2e/r2/teardown.ts',
 testDir:'./e2e/r2',outputDir:'test-results-r2',workers:1,retries:0,timeout:60_000,
 reporter:[['list'],['html',{outputFolder:'playwright-report-r2',open:'never'}]],
 use:{baseURL:'http://127.0.0.1:8018',channel:'chrome',trace:'retain-on-failure',screenshot:'only-on-failure'},
 webServer:{command:'.\\.venv\\Scripts\\python.exe -m tests.r2_fixture_server',url:'http://127.0.0.1:8018/api/health',reuseExistingServer:false,timeout:60_000},
});
