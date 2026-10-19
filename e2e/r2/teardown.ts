export default async function teardown(){
 await fetch('http://127.0.0.1:8018/__r2/shutdown',{method:'POST'}).catch(()=>{});
}
