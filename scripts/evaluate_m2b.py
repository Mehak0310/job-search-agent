import json
import time
from pathlib import Path
from job_agent.evaluation import evaluate
from job_agent.intelligence import SentenceTransformerProvider

if __name__ == "__main__":
    results={"hash_fallback":evaluate(),"trained_provider":{"status":"blocked"}}
    started=time.perf_counter()
    try:
        provider=SentenceTransformerProvider(revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",local_files_only=True)
        results["trained_provider"]={"status":"verified","model_id":provider.model_id,"revision":provider.version,"load_seconds":round(time.perf_counter()-started,4),"results":evaluate(provider)}
    except Exception as error:
        results["trained_provider"]={"status":"blocked","reason":type(error).__name__,"model_id":"sentence-transformers/all-MiniLM-L6-v2","revision":"1110a243fdf4706b3f48f1d95db1a4f5529b4d41","local_files_only":True}
    output=Path("artifacts/m2c-evaluation.json"); output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
    print(output)
