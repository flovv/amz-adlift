"""Custom exceptions for amz-flywheel data contracts and licensing."""


class AmzFlywheelError(Exception):
    """Base exception for all amz-flywheel errors."""


class SchemaMismatchError(AmzFlywheelError):
    """Raised when an input CSV/XLSX does not match any supported SQP, Ads, or Rank schema."""


class InsufficientHistoryError(AmzFlywheelError):
    """Raised when a keyword panel has fewer than the minimum required weekly observations (4 weeks)."""


class ProLicenseError(AmzFlywheelError):
    """Raised when a Pro econometric feature is invoked without a valid amz_flywheel_pro installation or license."""
