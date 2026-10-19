import {test,expect} from '@playwright/test';

test('notification center opens, preferences persist, schedules remain disabled',async({page,request})=>{
 await page.goto('/');
 await page.getByRole('button',{name:/Notifications \(/}).click();
 const center=page.getByRole('dialog',{name:'Batch notifications'});
 await expect(center).toBeVisible();
 await expect(center.getByRole('heading',{name:'Batch notifications'})).toBeVisible();
 await expect(center.getByRole('status')).not.toBeEmpty();
 await center.getByLabel('Enable sound while this page is open').check();
 await expect.poll(async()=> (await (await request.get('/api/notifications')).json()).preferences.sound).toBe(1);
 await center.getByRole('button',{name:'Close notifications'}).click();
 await expect(center).not.toBeVisible();
 const schedule=await request.post('/api/orchestration/schedules',{data:{stage:'NOTIFICATIONS',interval_seconds:3600,next_run:'2026-10-19T00:00:00+00:00'}});
 expect(schedule.ok()).toBeTruthy();expect((await schedule.json()).enabled).toBe(false);
 const plans=await (await request.get('/api/orchestration/schedules')).json();
 expect(plans.activation_enabled).toBe(false);
 expect(plans.items.every((p:any)=>p.enabled===0)).toBeTruthy();
 await page.reload();await page.getByRole('button',{name:/Notifications \(/}).click();
 await expect(page.getByLabel('Enable sound while this page is open')).toBeChecked();
});
