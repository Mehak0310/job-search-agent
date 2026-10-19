import { test as base, expect, open } from './fixtures';
export const view={job_key:'fixture-key',fit_label:'Strong fit',matching_skills:['Angular'],matching_reasons:['Angular matches the vacancy'],gaps:['Payroll verification pending'],employer_checks:[{label:'Payroll',state:'Needs research',detail:'Confirm direct payroll',owner:'Research',evidence_url:'https://example.com/evidence'}],verified_contacts:[{name:'Hiring team',email:'hiring@example.com'}],draft_status:'Automatic unsent drafting enabled',candidate_inputs:[],application_status:'Text prepared',submission_status:'Not submitted',next_action:'Review application',next_action_owner:'You',readiness:'READY_FOR_PORTAL_REVIEW',packet_id:'fixture-packet',draft_allowed:true,subject:'Role-specific subject',email_text:'Role-specific email',supporting_statement:'Angular component example',questions:[],vacancy_url:'https://example.com/jobs/123',browser_preparation:{id:'fixture-browser',state:'NEEDS_USER_ANSWER',updated_at:'2026-10-18T00:00:00Z',missing:['Surname'],documents:[]}};
export const job={id:'fixture-job',company:'Example',title:'Frontend fixture',location:'Noida',work_mode:'hybrid',published_at:null,match_score:85,status:'NEW',listing_kind:'IMPORTED',is_sample:false,description:'Build Angular components',match:{confidence:'HIGH',reasons:['Angular'],missing_requirements:['Payroll'],potential_disqualifiers:[]},sources:[{source:'fixture',source_job_id:'123',application_url:'https://example.com/jobs/123',listing_url:'https://example.com/jobs/123'}],history:[{status:'NEW',created_at:'2026-10-18T00:00:00Z'}],card:view,application_url:view.vacancy_url,canonical_application_url:view.vacancy_url};
export const packet={packet_id:'fixture-packet',job_id:job.id,company:job.company,title:job.title,status:'TEXT_PREPARED',current_version:1,missing_information:['direct_permanent_payroll'],fit_summary:['Angular component delivery'],gaps:['Payroll unknown'],application_url:view.vacancy_url};
export const browserRow={id:'fixture-browser',job_id:job.id,company:job.company,title:job.title,state:'NEEDS_USER_ANSWER',url:view.vacancy_url,target_id:'tab-fixture',inspection:{},missing:['Surname'],checks:['Payroll'],documents:[]};
export const test=base.extend<{portal:void}>({portal:[async({harness},use)=>{
 const replies=harness.replies;
 replies.set('GET /api/jobs',{body:{items:[job,{...job,id:'unprepared-job',title:'Unprepared fixture',card:{...view,packet_id:null,browser_preparation:null,draft_allowed:false}}],total:2,page:1,pages:1,has_next:false,has_previous:false}});
 replies.set('GET /api/jobs/'+job.id,{body:job});
 replies.set('GET /api/m3/packets',{body:[packet]});
 replies.set('GET /api/m3/packets/'+packet.packet_id,{body:{...packet,version_data:{...packet,subject:view.subject,email_text:view.email_text,email_html:'',supporting_statement:view.supporting_statement},questions:[],contacts:[]}});
 replies.set('GET /api/browser/applications',{body:[browserRow]});
 replies.set('GET /api/recommendations',{body:[{...job,recommendation_score:85,gate_state:'ELIGIBLE',recommendation_confidence:'HIGH',ai_state:'analyzed',recommendation_explanation:{why:['Angular fit'],matched_skills:['Angular'],missing_or_uncertain:['Payroll']}}]});
 replies.set('GET /api/sources',{body:[{id:'fixture-source',company:'Example',enabled:true,provider:'fixture',health:'OK',verified:false,india_relevant:null}]});
 replies.set('GET /api/discovery/latest',{body:null});
 replies.set('GET /api/candidate-profile/facts',{body:[{id:'fixture-fact',value:'Angular',status:'PENDING',source_ref:'fixture',confidence:1,category:'skills',extraction_id:'fixture-extraction'}]});
 await use();
},{auto:true}]});
export {expect,open};
