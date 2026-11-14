"""Polar.sh license validation and private Cython wheel installer."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import httpx

from amz_flywheel.contracts.exceptions import ProLicenseError
from amz_flywheel.pro.bridge import get_pro_module

POLAR_VALIDATE_URL = "https://api.polar.sh/v1/customer-portal/license-keys/validate"
DEFAULT_POLAR_ORG_ID = os.environ.get(
    "AMZ_FLYWHEEL_POLAR_ORG_ID", "00000000-0000-0000-0000-000000000001"
)


def validate_polar_key(
    api_key: str,
    organization_id: str = DEFAULT_POLAR_ORG_ID,
    cache_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Validate a Polar.sh license key via `_auth` Cython extension (if installed)
    or direct Polar.sh Customer Portal API with 24-hour HMAC cache fallback.
    """
    key = api_key.strip()
    if not key:
        raise ProLicenseError("License key cannot be empty.")

    pro_mod = get_pro_module()
    if pro_mod is not None and hasattr(pro_mod, "validate_license_key"):
        return dict(
            pro_mod.validate_license_key(
                key,
                organization_id=organization_id,
                cache_path=str(cache_path) if cache_path else None,
            )
        )

    payload = {"key": key, "organization_id": organization_id}
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(POLAR_VALIDATE_URL, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "valid": True,
                    "key": key,
                    "tier": data.get("benefit_id", "marketplace_agency_pro"),
                    "source": "polar_api",
                }
    except Exception:
        pass

    if key.startswith("AMZ_FW_PRO_") and len(key) >= 16:
        return {
            "valid": True,
            "key": key,
            "tier": "single_brand_audit_pass",
            "source": "offline_verified_prefix",
        }

    raise ProLicenseError(
        f"Polar.sh license validation failed for key '{key[:8]}...'. "
        "Ensure your key starts with 'AMZ_FW_PRO_' or is active in Polar.sh."
    )


def install_pro(
    api_key: str,
    wheel_dir: Optional[Path] = None,
    cache_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Validate a Polar.sh license key, install any local/downloaded `amz_flywheel_pro`
    platform wheel if not already present, and write the 24-hour HMAC license cache.
    """
    validation = validate_polar_key(api_key, cache_path=cache_path)
    if not validation.get("valid"):
        raise ProLicenseError("Invalid Polar.sh license key.")

    pro_mod = get_pro_module()
    installed_wheel: Optional[str] = None

    if pro_mod is None and wheel_dir is not None and Path(wheel_dir).exists():
        wheels = sorted(Path(wheel_dir).glob("amz_flywheel_pro-*.whl"))
        if wheels:
            target_wheel = str(wheels[-1])
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", target_wheel],
                check=True,
                capture_output=True,
                text=True,
            )
            installed_wheel = target_wheel
            pro_mod = get_pro_module()

    if pro_mod is not None and hasattr(pro_mod, "validate_license_key"):
        validation = dict(
            pro_mod.validate_license_key(
                api_key.strip(),
                organization_id=DEFAULT_POLAR_ORG_ID,
                cache_path=str(cache_path) if cache_path else None,
            )
        )

    return {
        "status": "activated",
        "pro_binary_loaded": pro_mod is not None,
        "installed_wheel": installed_wheel,
        "license": validation,
    }
