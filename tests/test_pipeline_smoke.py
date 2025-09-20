from fastapi.testclient import TestClient
from sirep.app.api import app

def test_pipeline_smoke():
    c = TestClient(app)
    # health
    assert c.get("/health").status_code == 200
    # run minimal pipeline
    steps = {"steps": ["ETAPA_1","ETAPA_2","ETAPA_3","ETAPA_4","ETAPA_10","ETAPA_11","ETAPA_12"]}
    r = c.post("/jobs/run", json=steps)
    assert r.status_code == 200
    data = r.json()["result"]
    assert "ETAPA_1_CAPTURA_PLANOS" in data