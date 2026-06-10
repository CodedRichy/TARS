from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from tars.genome.changelog import ChangelogManager
from tars.genome.models import ChangelogEntry, ChangeOperation, HeuristicStatus
from tars.genome.store import GenomeStore


@dataclass
class EntityDiff:
    entity_type: str
    entity_id: str
    changes: list[ChangelogEntry] = field(default_factory=list)

    @property
    def net_change(self) -> dict:
        if not self.changes:
            return {}
        result: dict = {}
        for entry in self.changes:
            for fld, val in entry.field_changes.items():
                if fld not in result:
                    result[fld] = {"old": val.get("old"), "new": val.get("new")}
                else:
                    result[fld]["new"] = val.get("new")
        return result

    @property
    def is_new(self) -> bool:
        return any(c.operation == ChangeOperation.CREATE for c in self.changes)


@dataclass
class BrainDiff:
    since: datetime
    new_entities: list[EntityDiff] = field(default_factory=list)
    changed_entities: list[EntityDiff] = field(default_factory=list)
    reverted_entities: list[EntityDiff] = field(default_factory=list)


class BrainVersioning:
    def __init__(self, store: GenomeStore, changelog: ChangelogManager) -> None:
        self.store = store
        self.changelog = changelog

    async def brain_log(self, limit: int = 50) -> list[ChangelogEntry]:
        return await self.changelog.get_log(entity_type="HEURISTIC", limit=limit)

    async def brain_diff(self, since: datetime) -> BrainDiff:
        entries = await self.changelog.get_entries_since(since)
        heuristic_entries = [e for e in entries if e.entity_type == "HEURISTIC"]

        by_entity: dict[str, list[ChangelogEntry]] = {}
        for e in heuristic_entries:
            by_entity.setdefault(e.entity_id, []).append(e)

        diff = BrainDiff(since=since)
        for eid, changes in by_entity.items():
            ed = EntityDiff(entity_type="HEURISTIC", entity_id=eid, changes=changes)
            if ed.is_new:
                diff.new_entities.append(ed)
            elif any(c.operation == ChangeOperation.REVERT for c in changes):
                diff.reverted_entities.append(ed)
            else:
                diff.changed_entities.append(ed)
        return diff

    async def revert_lesson(self, heuristic_id: str, reason: str = "user revert") -> bool:
        h = await self.store.get_heuristic(heuristic_id)
        if not h:
            return False

        old_status = h.status.value
        await self.store.update_heuristic_status(heuristic_id, HeuristicStatus.REVERTED)
        await self.store.zero_evidence_weights(heuristic_id)

        updated = await self.store.get_heuristic(heuristic_id)
        snapshot = json.loads(updated.model_dump_json()) if updated else {}

        await self.changelog.append(
            entity_type="HEURISTIC",
            entity_id=heuristic_id,
            operation=ChangeOperation.REVERT,
            field_changes={"status": {"old": old_status, "new": "REVERTED"}},
            reason=reason,
            snapshot=snapshot,
        )
        return True

    async def revert_to_date(self, target: datetime) -> list[str]:
        entries = await self.changelog.get_entries_since(target)
        heuristic_entries = [e for e in reversed(entries) if e.entity_type == "HEURISTIC"]
        reverted_ids: list[str] = []
        seen: set[str] = set()

        for entry in heuristic_entries:
            if entry.entity_id in seen:
                continue
            seen.add(entry.entity_id)
            if entry.operation == ChangeOperation.CREATE:
                await self.store.update_heuristic_status(entry.entity_id, HeuristicStatus.REVERTED)
                reverted_ids.append(entry.entity_id)
            elif entry.operation in (
                ChangeOperation.STATUS_CHANGE,
                ChangeOperation.UPDATE,
            ):
                old_status = entry.field_changes.get("status", {}).get("old")
                if old_status:
                    await self.store.update_heuristic_status(
                        entry.entity_id, HeuristicStatus(old_status)
                    )
                    reverted_ids.append(entry.entity_id)

        if reverted_ids:
            await self.changelog.append(
                entity_type="HEURISTIC",
                entity_id="batch",
                operation=ChangeOperation.REVERT,
                reason=f"revert to {target.isoformat()}, {len(reverted_ids)} heuristics affected",
            )
        return reverted_ids
