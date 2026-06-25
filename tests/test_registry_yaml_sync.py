from pathlib import Path

import yaml

from metrics.registry import REGISTRY

YAML_PATH = Path(__file__).resolve().parents[1] / "semantic" / "rm_metrics.yml"


def _measure_ids() -> set[str]:
    docs = yaml.safe_load_all(YAML_PATH.read_text())
    ids: set[str] = set()
    for doc in docs:
        if not doc:
            continue
        for measure in doc.get("measures", []) or []:
            ids.add(measure["id"])
    return ids


def test_every_registry_metric_exists_in_yaml():
    yaml_ids = _measure_ids()
    orphans = [mid for mid in REGISTRY if mid not in yaml_ids]
    assert not orphans, f"registry metrics missing from rm_metrics.yml: {orphans}"
