"""The handoff panel: registry and annotations agree with the code, nothing secret leaks."""
import copy

from app.panel import facts as F
from app.panel.build import build_panel, check, load
from app.panel.source import Source


def test_registry_and_annotations_match_the_code():
    assert check() == []


def test_checker_catches_drift():
    src = Source()
    reg, ann = load(src)
    f = F.collect(src)
    reg2, ann2 = copy.deepcopy(reg), copy.deepcopy(ann)
    reg2["etapas"][0]["codigo"].append("app/agents/collect.py::no_such_function")
    reg2["etapas"][0]["pasos_registrados"].remove("recolector")
    del ann2["cola"]["titulo_cargado"]
    joined = " | ".join(check(src, f, reg2, ann2))
    assert "no_such_function" in joined and "símbolo inexistente" in joined
    assert "paso 'recolector'" in joined
    assert "titulo_cargado" in joined


def test_panel_has_every_view_and_no_secret_values(monkeypatch, tmp_path):
    for var, value in {"CHAT_API_KEY": "sk-panel-test-secret", "ADMIN_PASSWORD": "panel-test-password",
                       "DATABASE_URL": "postgresql://u:panel-test-dbpass@example.invalid/db"}.items():
        monkeypatch.setenv(var, value)
    html, problems = build_panel(tmp_path / "panel.html", with_live=False)
    assert problems == []
    for view in ("vision", "pipeline", "agentes", "compuertas", "cola", "datos", "chat", "infra", "runbook",
                 "costos", "extender", "deuda", "glosario"):
        assert f'id="{view}"' in html
    for secret in ("sk-panel-test-secret", "panel-test-password", "panel-test-dbpass"):
        assert secret not in html
    # every agent run type, queue type and table found in the code appears in the panel
    f = F.collect(Source())
    for r in f["agent"]["reviews"]:
        assert r["tipo"] in html
    for t in f["models"]["tables"]:
        assert f'id="tabla-{t}"' in html
