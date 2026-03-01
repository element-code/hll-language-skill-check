from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class LabeledMetric:
    value: float
    label: str


class ResultCache:
    def __init__(self):
        self.data = defaultdict(dict)

    def update(self, server_id: str, resolver_id: str, result: Result):
        self.data[server_id][resolver_id] = result

    def get_all(self):
        return self.data

    def get(self, server_id: str, resolver_id: str) -> Result | None:
        return self.data.get(server_id, {}).get(resolver_id, None)
