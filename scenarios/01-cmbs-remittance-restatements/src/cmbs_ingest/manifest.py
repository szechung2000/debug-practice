"""Landing-zone manifest.

The SFTP collector writes one manifest row per file it pulls from a servicer
portal. A servicer can resend a file for the same deal and period (a
restatement). The manifest is the only record of when each copy arrived.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

FILE_RE = re.compile(r"^(?P<deal>[A-Z0-9]+(?:-[A-Z0-9]+)*)_(?P<period>\d{6})_LPU(?:_R(?P<rev>\d+))?\.csv$")


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class ManifestEntry:
    file_name: str
    servicer: str
    deal_id: str
    period: str           # YYYYMM determination period
    received_at: str      # as written by the collector, kept verbatim for audit
    sha256: str
    path: Path

    @property
    def is_restatement(self) -> bool:
        m = FILE_RE.match(self.file_name)
        return bool(m and m.group("rev"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(manifest_path: Path, accepted_servicers: tuple[str, ...]) -> list[ManifestEntry]:
    if not manifest_path.exists():
        raise ManifestError(f"manifest not found: {manifest_path}")
    landing = manifest_path.parent
    entries: list[ManifestEntry] = []
    seen_hashes: dict[str, str] = {}
    with manifest_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"file_name", "servicer", "received_at", "sha256"} - set(reader.fieldnames or [])
        if missing:
            raise ManifestError(f"manifest is missing columns: {sorted(missing)}")
        for line_no, row in enumerate(reader, start=2):
            name = row["file_name"].strip()
            m = FILE_RE.match(name)
            if not m:
                log.warning("manifest line %d: unexpected file name %r, skipped", line_no, name)
                continue
            servicer = row["servicer"].strip().upper()
            if servicer not in accepted_servicers:
                log.warning("manifest line %d: servicer %s is not onboarded, skipped", line_no, servicer)
                continue
            path = landing / name
            if not path.exists():
                raise ManifestError(f"manifest line {line_no}: file {name} is not in the landing zone")
            actual = _sha256(path)
            if actual != row["sha256"].strip():
                raise ManifestError(f"manifest line {line_no}: checksum mismatch for {name}")
            if actual in seen_hashes:
                log.info("file %s is a byte-identical copy of %s, skipped", name, seen_hashes[actual])
                continue
            seen_hashes[actual] = name
            entries.append(ManifestEntry(
                file_name=name,
                servicer=servicer,
                deal_id=m.group("deal"),
                period=m.group("period"),
                received_at=row["received_at"].strip(),
                sha256=actual,
                path=path,
            ))
    log.info("manifest: %d usable files (%d restatements)",
             len(entries), sum(e.is_restatement for e in entries))
    return entries


def filter_periods(entries: list[ManifestEntry], periods: set[str] | None) -> list[ManifestEntry]:
    if not periods:
        return entries
    return [e for e in entries if e.period in periods]
