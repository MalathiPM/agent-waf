from pathlib import Path
import yaml
from waf.models import Policy


def load_policy(path: str | Path) -> Policy:
    with open(path, encoding="utf-8") as f:
        return Policy.model_validate(yaml.safe_load(f))
