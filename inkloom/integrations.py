"""Small, replaceable interfaces for future integrations.

Nothing here is connected, and nothing creates fake endpoints or credentials.
Authentication, authorisation, persistence, and delivery must be implemented
server-side in a later build; hiding a control is never enough.
"""
from __future__ import annotations


class NotConnected(RuntimeError):
    """Raised by every unconnected integration in this build."""


class AuthAdapter:
    """Future verified authentication (e.g. Google sign-in)."""

    implemented = False

    def current_user(self):
        """Return the verified user for this request, or None."""
        raise NotConnected("Authentication is not connected in this build.")


class DraftRepository:
    """Future persistent draft storage."""

    implemented = False

    def save(self, *, guest_or_user, draft):
        raise NotConnected("Permanent draft storage is not connected in this build.")

    def load(self, *, guest_or_user, draft_id):
        raise NotConnected("Permanent draft storage is not connected in this build.")


class RuleRepository:
    """Future approved-rule management (never fed by imported packs)."""

    implemented = False

    def approve(self, *, rule_set_id, rules, actor):
        raise NotConnected("Approved-rule management is not connected in this build.")


class ContactService:
    """Future contact-form delivery."""

    implemented = False

    def deliver(self, *, name, email, topic, message):
        raise NotConnected("Contact delivery is not connected in this build.")


class IssueService:
    """Future issue-report delivery and reference generation."""

    implemented = False

    def deliver(self, *, report):
        raise NotConnected("Issue submission is not connected in this build.")


def describe_interfaces():
    """List the prepared interfaces and their state (for docs/tests)."""
    return {
        "authentication": AuthAdapter.implemented,
        "draft_persistence": DraftRepository.implemented,
        "approved_rules": RuleRepository.implemented,
        "contact_delivery": ContactService.implemented,
        "issue_submission": IssueService.implemented,
    }
