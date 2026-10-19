export default async function teardown(){
 await fetch('http://127.0.0.1:8019/__ui/shutdown',{method:'POST'}).catch(()=>{});
}
