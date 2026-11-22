"""Custom exceptions for amz-adlift data contracts and licensing."""


class AmzAdliftError(Exception):
    """Base exception for all amz-adlift errors."""


class SchemaMismatchError(AmzAdliftError):
    """Raised when an input CSV/XLSX does not match any supported SQP, Ads, or Rank schema."""


class InsufficientHistoryError(AmzAdliftError):
    """Raised when a keyword panel has fewer than the minimum required weekly observations (4 weeks)."""


class ProLicenseError(AmzAdliftError):
    """Raised when a Pro econometric feature is invoked without a valid amz_adlift_pro installation or license."""
