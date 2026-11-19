"""Polar.sh license validation, platform tag detection & private Cython wheel installer."""

from __future__ import annotations

import hashlib
import os
import platform
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
DEFAULT_WHEEL_MANIFEST_URL = os.environ.get("AMZ_FLYWHEEL_WHEEL_MANIFEST_URL", "")


def _is_dev_test_mode() -> bool:
    """Explicit opt-in flag for local CI/pytest harnesses; disabled in production."""
    return os.environ.get("AMZ_FLYWHEEL_DEV_TEST_MODE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def detect_wheel_tags() -> dict[str, str]:
    """
    Detect the active Python ABI tag (e.g. `cp311`) and OS/CPU platform tag
    (`manylinux`, `macosx_arm64`, `macosx_x86_64`, `win_amd64`) for selecting
    the matching pre-compiled `amz_flywheel_pro` binary wheel.
    """
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    sys_name = platform.system().lower()
    machine = platform.machine().lower()

    if sys_name == "darwin":
        plat_tag = "macosx_arm64" if machine in ("arm64", "aarch64") else "macosx_x86_64"
    elif sys_name == "windows":
        plat_tag = "win_amd64"
    else:
        plat_tag = "manylinux_aarch64" if machine in ("arm64", "aarch64") else "manylinux_x86_64"

    return {
        "python_tag": py_tag,
        "platform_tag": plat_tag,
        "os": sys_name,
        "arch": machine,
    }


def _match_wheel_entry(
    entries: list[dict[str, Any]], tags: dict[str, str]
) -> Optional[dict[str, Any]]:
    """Select the wheel manifest/Polar file entry matching the local Python & platform tags."""
    py_tag = tags["python_tag"]
    plat_tag = tags["platform_tag"]
    plat_prefix = plat_tag.split("_")[0]  # e.g. manylinux, macosx, win
    arch_suffix = plat_tag.split("_")[-1]  # e.g. x86_64, arm64, amd64

    for entry in entries:
        fname = str(entry.get("filename") or entry.get("name") or entry.get("url") or "").lower()
        if not fname.endswith(".whl"):
            continue
        if py_tag in fname and plat_prefix in fname and arch_suffix in fname:
            return entry

    # Fallback: match Python tag + OS prefix (e.g. universal2 macOS wheel)
    for entry in entries:
        fname = str(entry.get("filename") or entry.get("name") or entry.get("url") or "").lower()
        if fname.endswith(".whl") and py_tag in fname and plat_prefix in fname:
            return entry
    return None


def _verify_sha256(file_path: Path, expected_sha256: str) -> None:
    """Verify SHA-256 digest of a downloaded wheel binary."""
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    if digest.lower() != expected_sha256.strip().lower():
        file_path.unlink(missing_ok=True)
        raise ProLicenseError(
            f"Wheel SHA-256 verification failed for {file_path.name}: "
            f"expected {expected_sha256[:16]}..., got {digest[:16]}..."
        )


def resolve_and_download_wheel(
    api_key: str,
    validation_payload: Optional[dict[str, Any]] = None,
    wheel_url: Optional[str] = None,
    manifest_url: Optional[str] = None,
    dest_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Download the matching platform `amz_flywheel_pro` wheel from either:
      1. An explicit `wheel_url`,
      2. Polar.sh benefit file entries returned during key validation, or
      3. A JSON wheel manifest (`manifest_url` or `AMZ_FLYWHEEL_WHEEL_MANIFEST_URL`).
    """
    target_dir = Path(dest_dir) if dest_dir else (Path.home() / ".amz_flywheel" / "wheels")
    target_dir.mkdir(parents=True, exist_ok=True)
    tags = detect_wheel_tags()

    chosen_url: Optional[str] = wheel_url
    chosen_filename: Optional[str] = None
    expected_sha256: Optional[str] = None

    if not chosen_url and validation_payload:
        files = list(validation_payload.get("files") or [])
        matched = _match_wheel_entry(files, tags)
        if matched:
            chosen_url = str(matched.get("download_url") or matched.get("url") or "")
            chosen_filename = str(matched.get("filename") or matched.get("name") or "")
            expected_sha256 = matched.get("sha256")

    eff_manifest_url = manifest_url or DEFAULT_WHEEL_MANIFEST_URL
    if not chosen_url and eff_manifest_url:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    eff_manifest_url,
                    headers={"Authorization": f"Bearer {api_key.strip()}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    entries = data.get("wheels", data) if isinstance(data, dict) else data
                    if isinstance(entries, list):
                        matched = _match_wheel_entry(entries, tags)
                        if matched:
                            chosen_url = str(matched.get("url") or matched.get("download_url") or "")
                            chosen_filename = str(matched.get("filename") or "")
                            expected_sha256 = matched.get("sha256")
        except Exception as exc:
            raise ProLicenseError(
                f"Failed to fetch Pro wheel manifest from {eff_manifest_url}: {exc}"
            ) from exc

    if not chosen_url:
        return None

    fname = chosen_filename or Path(chosen_url.split("?")[0]).name
    if not fname.endswith(".whl"):
        fname = f"amz_flywheel_pro-0.1.0-{tags['python_tag']}-{tags['python_tag']}-{tags['platform_tag']}.whl"

    dest_file = target_dir / fname
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(
                chosen_url,
                headers={"Authorization": f"Bearer {api_key.strip()}"},
            )
            resp.raise_for_status()
            dest_file.write_bytes(resp.content)
    except Exception as exc:
        raise ProLicenseError(
            f"Failed to download amz_flywheel_pro wheel from {chosen_url}: {exc}"
        ) from exc

    if expected_sha256:
        _verify_sha256(dest_file, str(expected_sha256))

    return dest_file


def validate_polar_key(
    api_key: str,
    organization_id: str = DEFAULT_POLAR_ORG_ID,
    cache_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Validate a Polar.sh license key via `_auth` Cython extension (if installed)
    or direct Polar.sh Customer Portal API.

    Offline prefix bypass is disabled in production and only allowed when
    `AMZ_FLYWHEEL_DEV_TEST_MODE=1` is explicitly set for test suites.
    """
    key = api_key.strip()
    if not key:
        raise ProLicenseError("License key cannot be empty.")

    org_id = os.environ.get("AMZ_FLYWHEEL_POLAR_ORG_ID", organization_id)
    pro_mod = get_pro_module()
    if pro_mod is not None and hasattr(pro_mod, "validate_license_key"):
        try:
            return dict(
                pro_mod.validate_license_key(
                    key,
                    organization_id=org_id,
                    cache_path=str(cache_path) if cache_path else None,
                )
            )
        except (PermissionError, ValueError) as exc:
            raise ProLicenseError(str(exc)) from exc

    payload = {"key": key, "organization_id": org_id}
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(POLAR_VALIDATE_URL, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                status_val = str(data.get("status", "granted")).lower()
                if status_val in ("granted", "active", "valid"):
                    return {
                        "valid": True,
                        "key": key,
                        "tier": data.get("benefit_id", "marketplace_agency_pro"),
                        "source": "polar_api",
                        "files": list(data.get("files", []) or []),
                    }
    except Exception:
        pass

    if _is_dev_test_mode() and key.startswith("AMZ_FW_PRO_") and len(key) >= 16:
        return {
            "valid": True,
            "key": key,
            "tier": "marketplace_agency_pro"
            if "AGENCY" in key.upper()
            else "single_brand_audit_pass",
            "source": "dev_test_mode",
            "files": [],
        }

    raise ProLicenseError(
        f"Polar.sh license validation failed for key '{key[:8]}...'. "
        "Ensure your subscription is active in Polar.sh."
    )


def install_pro(
    api_key: str,
    wheel_dir: Optional[Path] = None,
    wheel_url: Optional[str] = None,
    manifest_url: Optional[str] = None,
    cache_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Validate a Polar.sh license key, locate or download the matching platform
    `amz_flywheel_pro` Cython wheel if not already present, install it, and write
    the 24-hour HMAC-SHA256 license cache.
    """
    validation = validate_polar_key(api_key, cache_path=cache_path)
    if not validation.get("valid"):
        raise ProLicenseError("Invalid Polar.sh license key.")

    pro_mod = get_pro_module()
    installed_wheel: Optional[str] = None
    target_wheel_path: Optional[Path] = None

    if pro_mod is None or wheel_url is not None or wheel_dir is not None:
        if wheel_dir is not None and Path(wheel_dir).exists():
            tags = detect_wheel_tags()
            local_entries = [
                {"filename": p.name, "path": p}
                for p in sorted(Path(wheel_dir).glob("amz_flywheel_pro-*.whl"))
            ]
            matched = _match_wheel_entry(local_entries, tags)
            if matched:
                target_wheel_path = Path(matched["path"])
            elif local_entries:
                target_wheel_path = Path(local_entries[-1]["path"])

        if target_wheel_path is None:
            target_wheel_path = resolve_and_download_wheel(
                api_key=api_key,
                validation_payload=validation,
                wheel_url=wheel_url,
                manifest_url=manifest_url,
            )

        if target_wheel_path is not None and target_wheel_path.exists():
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--force-reinstall",
                    "--no-deps",
                    str(target_wheel_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            installed_wheel = str(target_wheel_path)
            pro_mod = get_pro_module()

    if pro_mod is not None and hasattr(pro_mod, "validate_license_key"):
        try:
            validation = dict(
                pro_mod.validate_license_key(
                    api_key.strip(),
                    organization_id=os.environ.get(
                        "AMZ_FLYWHEEL_POLAR_ORG_ID", DEFAULT_POLAR_ORG_ID
                    ),
                    cache_path=str(cache_path) if cache_path else None,
                )
            )
        except (PermissionError, ValueError) as exc:
            raise ProLicenseError(str(exc)) from exc

    return {
        "status": "activated",
        "pro_binary_loaded": pro_mod is not None,
        "platform_tags": detect_wheel_tags(),
        "installed_wheel": installed_wheel,
        "license": validation,
    }
