from dataclasses import dataclass


@dataclass
class UpdateResult:
    inserted_count: int | None
    updated_count: int | None
