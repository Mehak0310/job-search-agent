import json
from pathlib import Path
from job_agent.evaluation import evaluate

if __name__ == "__main__":
    output=Path("artifacts/m2b-evaluation.json"); output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(evaluate(),indent=2)+"\n",encoding="utf-8")
    print(output)
