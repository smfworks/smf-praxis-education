"""SMF Praxis Education vertical — registration module.

This package is the private paid Education / School System vertical build
for Praxis. It depends on the open-core ``smf-praxis`` base and registers
the education vertical's spec and eval cases with the base's
:mod:`hybridagent.verticals.registry` on import.

Installation::

    pip install praxis-agent            # open-core base (public, MIT)
    pip install praxis-education        # this vertical (private, commercial)

Activating the vertical lights up:

  * the ``school_system`` vertical pack (institutional education: persona +
    knowledge + SPED + privacy + attestation + vendor + records + comms
    modules),
  * the ``vertical.school_system.*`` eval cases (draft-not-decide, NY 2-d
    privacy, educator attestation, parent triage, vendor hygiene),
  * the ``vertical.education.*`` autonomous tutor persona eval cases.

Compliance mode: ``school_system`` enforced (READ + DRAFT autonomous; SEND
+ DESTRUCTIVE held). ``education`` tutor is autonomous (READ + DRAFT
autonomous; DESTRUCTIVE held). The School System persona carries SPED
FAPE/placement/eligibility guardrails, NY Ed Law §2-d privacy, and
13-state educator attestation.
"""

from __future__ import annotations

from .registration import register

__version__ = "0.1.0"

__all__ = ["register", "__version__"]

register()