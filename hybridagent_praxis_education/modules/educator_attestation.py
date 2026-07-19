"""Educator attestation for consequential school actions (Gap E4).

School-system analogue of clinical_attestation (never-write-to-chart):

- Final grade posts, IEP adoption, parent academic SEND, discipline letters,
  and external records releases require a recorded educator/admin attestation
  before the action may proceed.
- Mandatory reports may be **drafted** and **reminded** but Praxis is never
  the reporter of record.

The governance broker holds SEND; this ledger is the evidence surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ArtifactType = Literal[
    "grade_post",
    "iep_adoption",
    "iep_amendment",
    "parent_academic_message",
    "discipline_letter",
    "records_release",
    "pwn",
    "mandatory_report_draft",
    "other",
]

AttestationType = Literal["signed", "amended", "rejected"]


@dataclass(frozen=True)
class EducationDraft:
    draft_id: str
    artifact_type: ArtifactType
    student_id: str
    school_id: str
    content_hash: str
    drafted_by: str = "praxis"
    drafted_at: float = 0.0
    state: str = ""


@dataclass(frozen=True)
class EducatorAttestation:
    attestation_id: str
    draft_id: str
    educator_id: str
    role: str  # teacher_of_record | case_manager | admin | registrar
    attestation_type: AttestationType
    attested_at: float
    notes: str = ""


class EducatorAttestationError(Exception):
    """Chart/SIS/parent SEND blocked without valid attestation."""


# Roles authorized to attest each artifact type
_REQUIRED_ROLES: dict[str, frozenset[str]] = {
    "grade_post": frozenset({"teacher_of_record", "admin"}),
    "iep_adoption": frozenset({"case_manager", "admin"}),
    "iep_amendment": frozenset({"case_manager", "admin"}),
    "parent_academic_message": frozenset({
        "teacher_of_record", "case_manager", "admin", "counselor",
    }),
    "discipline_letter": frozenset({"admin"}),
    "records_release": frozenset({"registrar", "admin"}),
    "pwn": frozenset({"case_manager", "admin"}),
    "mandatory_report_draft": frozenset({
        "teacher_of_record", "admin", "counselor", "case_manager",
    }),
    "other": frozenset({
        "teacher_of_record", "case_manager", "admin", "registrar", "counselor",
    }),
}

# Artifact types that may never be auto-executed even with attestation alone
# (mandatory report filing remains human-only as reporter of record)
_NEVER_AUTO_EXECUTE = frozenset({"mandatory_report_draft"})


class EducatorAttestationLedger:
    def __init__(self) -> None:
        self._drafts: dict[str, EducationDraft] = {}
        self._attestations: list[EducatorAttestation] = []

    def register_draft(self, draft: EducationDraft) -> None:
        self._drafts[draft.draft_id] = draft

    def get_draft(self, draft_id: str) -> EducationDraft | None:
        return self._drafts.get(draft_id)

    def attest(self, attestation: EducatorAttestation) -> EducatorAttestation:
        draft = self._drafts.get(attestation.draft_id)
        if draft is None:
            raise EducatorAttestationError(
                f"cannot attest draft {attestation.draft_id} — not registered"
            )
        allowed = _REQUIRED_ROLES.get(draft.artifact_type, frozenset())
        if attestation.role not in allowed:
            raise EducatorAttestationError(
                f"role {attestation.role!r} cannot attest "
                f"{draft.artifact_type} (allowed: {sorted(allowed)})"
            )
        # Idempotent signed/amended
        existing = [
            a for a in self._attestations
            if a.draft_id == attestation.draft_id
            and a.attestation_type in ("signed", "amended")
        ]
        if existing and attestation.attestation_type in ("signed", "amended"):
            return existing[0]
        self._attestations.append(attestation)
        return attestation

    def can_execute(self, draft_id: str) -> bool:
        draft = self._drafts.get(draft_id)
        if draft is None:
            return False
        if draft.artifact_type in _NEVER_AUTO_EXECUTE:
            return False  # human files mandatory reports
        return any(
            a.draft_id == draft_id and a.attestation_type in ("signed", "amended")
            for a in self._attestations
        )

    def require_execute(self, draft_id: str) -> None:
        draft = self._drafts.get(draft_id)
        if draft is not None and draft.artifact_type in _NEVER_AUTO_EXECUTE:
            raise EducatorAttestationError(
                f"mandatory_report_draft {draft_id} may be drafted and "
                f"reminded only — Praxis is never the reporter of record"
            )
        if not self.can_execute(draft_id):
            raise EducatorAttestationError(
                f"execution blocked for draft {draft_id} — no signed/amended "
                f"educator attestation"
            )

    def pending_drafts(self) -> list[EducationDraft]:
        signed = {
            a.draft_id for a in self._attestations
            if a.attestation_type in ("signed", "amended")
        }
        rejected = {
            a.draft_id for a in self._attestations
            if a.attestation_type == "rejected"
        }
        return [
            d for d in self._drafts.values()
            if d.draft_id not in signed and d.draft_id not in rejected
        ]
