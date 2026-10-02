from dataclasses import dataclass


@dataclass
class UpdateResult:
    inserted_count: int
    updated_count: int
