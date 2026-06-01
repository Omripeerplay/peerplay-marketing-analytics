"""
AppLovin Axon Campaign Management API Client

Credentials are loaded from environment variables:
  - AXON_API_KEY
  - AXON_ACCOUNT_ID

Never hardcode or commit API keys.
"""

import os
import time
import json
import requests
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode


BASE_URL = "https://api.ads.axon.ai/manage/v1"

# Rate limit: 1000 requests / 60 seconds
_request_timestamps: list[float] = []
RATE_LIMIT = 1000
RATE_WINDOW = 60


def _get_credentials() -> tuple[str, str]:
    api_key = os.environ.get("AXON_API_KEY")
    account_id = os.environ.get("AXON_ACCOUNT_ID")
    if not api_key:
        raise EnvironmentError("AXON_API_KEY environment variable is not set")
    if not account_id:
        raise EnvironmentError("AXON_ACCOUNT_ID environment variable is not set")
    return api_key, account_id


def _rate_limit_wait():
    """Enforce rate limit of 1000 requests per 60 seconds."""
    now = time.time()
    # Remove timestamps older than the rate window
    while _request_timestamps and _request_timestamps[0] < now - RATE_WINDOW:
        _request_timestamps.pop(0)
    if len(_request_timestamps) >= RATE_LIMIT:
        sleep_time = _request_timestamps[0] + RATE_WINDOW - now + 0.1
        if sleep_time > 0:
            print(f"Rate limit approaching, waiting {sleep_time:.1f}s...")
            time.sleep(sleep_time)
    _request_timestamps.append(time.time())


def _request(method: str, endpoint: str, params: Optional[dict] = None,
             json_body: Optional[dict] = None, files=None) -> dict:
    """Make an authenticated request to the Axon API."""
    api_key, account_id = _get_credentials()
    _rate_limit_wait()

    url = f"{BASE_URL}/{endpoint}"
    base_params = {"account_id": account_id}
    if params:
        base_params.update(params)

    headers = {"Authorization": api_key}
    if json_body and not files:
        headers["Content-Type"] = "application/json"

    response = requests.request(
        method=method,
        url=url,
        params=base_params,
        headers=headers,
        json=json_body if not files else None,
        files=files,
    )

    # Check for Axon-specific errors
    error_code = response.headers.get("x-al-error-code")
    error_msg = response.headers.get("x-al-error-message")
    trace_id = response.headers.get("X-TRACE-ID", "unknown")

    if response.status_code == 429:
        raise Exception(
            f"Rate limited by Axon API. Retry after 10 minutes. "
            f"Trace ID: {trace_id}"
        )

    if response.status_code >= 400:
        raise Exception(
            f"Axon API error {response.status_code}: "
            f"code={error_code}, message={error_msg}, "
            f"trace_id={trace_id}, body={response.text}"
        )

    if response.text:
        return response.json()
    return {}


# ──────────────────────────────────────────────
# Campaign Endpoints
# ──────────────────────────────────────────────

def list_campaigns(ids: Optional[list[int]] = None,
                   hashed_ids: Optional[list[str]] = None,
                   page: int = 1, size: int = 100) -> dict:
    """List campaigns. Returns paginated campaign objects."""
    params = {"page": str(page), "size": str(size)}
    if ids:
        params["ids"] = ",".join(str(i) for i in ids)
    if hashed_ids:
        params["hashed_ids"] = ",".join(hashed_ids)
    return _request("GET", "campaign/list", params=params)


def list_all_campaigns() -> list[dict]:
    """Fetch all campaigns across all pages."""
    all_campaigns = []
    page = 1
    while True:
        result = list_campaigns(page=page, size=100)
        campaigns = result if isinstance(result, list) else result.get("campaigns", result.get("data", []))
        if not campaigns:
            break
        all_campaigns.extend(campaigns)
        if len(campaigns) < 100:
            break
        page += 1
    return all_campaigns


def create_campaign(name: str, platform: str, package_name: str,
                    start_date: str, budget: dict, goal: dict,
                    bidding_strategy: str, targeting: list[dict],
                    tracking: dict, itunes_id: Optional[int] = None,
                    end_date: Optional[str] = None) -> dict:
    """Create a new campaign."""
    body = {
        "name": name,
        "type": "APP",
        "platform": platform,
        "package_name": package_name,
        "start_date": start_date,
        "budget": budget,
        "goal": goal,
        "bidding_strategy": bidding_strategy,
        "targeting": targeting,
        "tracking": tracking,
    }
    if itunes_id:
        body["itunes_id"] = itunes_id
    if end_date:
        body["end_date"] = end_date
    return _request("POST", "campaign/create", json_body=body)


def update_campaign(campaign_id: int, **kwargs) -> dict:
    """Update a campaign. Pass any updatable fields as kwargs.

    Updatable fields: name, status, budget, goal, tracking, targeting, end_date
    """
    body = {"id": campaign_id, **kwargs}
    return _request("POST", "campaign/update", json_body=body)


def pause_campaign(campaign_id: int) -> dict:
    """Pause a campaign."""
    return update_campaign(campaign_id, status="PAUSED")


def resume_campaign(campaign_id: int) -> dict:
    """Resume/unpause a campaign."""
    return update_campaign(campaign_id, status="LIVE")


def update_campaign_budget(campaign_id: int, daily_budget: str,
                           country_budgets: Optional[dict] = None) -> dict:
    """Update campaign budget. Use country_budgets for per-country control."""
    if country_budgets:
        budget = {"country_code_to_daily_budget": country_budgets}
    else:
        budget = {"daily_budget_for_all_countries": daily_budget}
    return update_campaign(campaign_id, budget=budget)


# ──────────────────────────────────────────────
# Creative Set Endpoints
# ──────────────────────────────────────────────

def list_creative_sets(ids: Optional[list[str]] = None,
                       page: int = 1, size: int = 100) -> dict:
    """List creative sets."""
    params = {"page": str(page), "size": str(size)}
    if ids:
        params["ids"] = ",".join(ids)
    return _request("GET", "creative_set/list", params=params)


def list_creative_sets_by_campaign(campaign_id: Optional[int] = None) -> dict:
    """List creative sets organized by campaign."""
    params = {}
    if campaign_id:
        params["campaign_id"] = str(campaign_id)
    return _request("GET", "creative_set/list_by_campaign_id", params=params)


def create_creative_set(name: str, assets: list[dict],
                        campaign_id: Optional[str] = None,
                        languages: Optional[list[str]] = None,
                        countries: Optional[list[str]] = None,
                        product_page: Optional[str] = None) -> dict:
    """Create a new creative set."""
    body = {"type": "APP", "name": name, "assets": assets}
    if campaign_id:
        body["campaign_id"] = campaign_id
    if languages:
        body["languages"] = languages
    if countries:
        body["countries"] = countries
    if product_page:
        body["product_page"] = product_page
    return _request("POST", "creative_set/create", json_body=body)


def update_creative_set(creative_set_id: str, **kwargs) -> dict:
    """Update a creative set."""
    body = {"id": creative_set_id, "type": "APP", **kwargs}
    return _request("POST", "creative_set/update", json_body=body)


def pause_creative_set(creative_set_id: str) -> dict:
    """Pause a creative set (stops serving across all campaigns)."""
    return update_creative_set(creative_set_id, status="PAUSED")


def resume_creative_set(creative_set_id: str) -> dict:
    """Resume a paused creative set."""
    return update_creative_set(creative_set_id, status="LIVE")


def clone_creative_set(campaign_id: str, creative_set_id: str,
                       status: str = "LIVE") -> dict:
    """Clone a creative set to a campaign."""
    body = {
        "campaign_id": campaign_id,
        "creative_set_id": creative_set_id,
        "status": status,
    }
    return _request("POST", "creative_set/clone", json_body=body)


def add_creative_sets_to_campaigns(campaign_ids: list[str],
                                    creative_set_ids: list[str]) -> dict:
    """Add creative sets to campaigns (max 20 campaigns, 50 creative sets)."""
    body = {"campaign_ids": campaign_ids, "creative_set_ids": creative_set_ids}
    return _request("POST", "creative_set/add-to-campaigns", json_body=body)


def remove_creative_sets_from_campaigns(campaign_ids: list[str],
                                         creative_set_id: str) -> dict:
    """Remove a creative set from specific campaigns."""
    body = {"campaign_ids": campaign_ids, "creative_set_id": creative_set_id}
    return _request("POST", "creative_set/remove-from-campaigns", json_body=body)


def remove_creative_sets_from_all_campaigns(creative_set_ids: list[str]) -> dict:
    """Remove creative sets from all campaigns (max 50)."""
    body = {"creative_set_ids": creative_set_ids}
    return _request("POST", "creative_set/remove-from-all-campaigns", json_body=body)


# ──────────────────────────────────────────────
# Asset Endpoints
# ──────────────────────────────────────────────

def list_assets(ids: Optional[list[str]] = None,
                resource_type: Optional[str] = None,
                page: int = 1, size: int = 100) -> dict:
    """List assets. resource_type: IMAGE, VIDEO, HTML (auto-uppercased)."""
    params = {"page": str(page), "size": str(size)}
    if ids:
        params["ids"] = ",".join(ids)
    if resource_type:
        params["resource_type"] = resource_type.upper()
    return _request("GET", "asset/list", params=params)


def upload_assets(file_paths: list[str]) -> dict:
    """Upload asset files (max 40 files, 10 GB total, 1 GB per file).

    Supported types: text/html, image/gif, image/jpeg, image/png, video/mp4, video/quicktime
    Returns an upload_id to check status with check_upload_status().
    """
    if len(file_paths) > 40:
        raise ValueError("Maximum 40 files per upload")

    mime_map = {
        ".html": "text/html",
        ".gif": "image/gif",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
    }

    files = []
    for fp in file_paths:
        path = Path(fp)
        ext = path.suffix.lower()
        mime = mime_map.get(ext)
        if not mime:
            raise ValueError(
                f"Unsupported file type '{ext}' for {path.name}. "
                f"Supported: {', '.join(mime_map.keys())}"
            )
        files.append(("file", (path.name, open(fp, "rb"), mime)))

    try:
        return _request("POST", "asset/upload", files=files)
    finally:
        for _, (_, f, _) in files:
            f.close()


def check_upload_status(upload_id: str) -> dict:
    """Check the status of an asset upload."""
    params = {"upload_id": upload_id}
    return _request("GET", "asset/upload_result", params=params)


def wait_for_upload(upload_id: str, timeout: int = 300, poll_interval: int = 5) -> dict:
    """Poll upload status until all files are processed or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        result = check_upload_status(upload_id)
        summary = result.get("summary", {})
        pending = summary.get("PENDING", 0)
        if pending == 0:
            return result
        print(f"Upload in progress... {pending} files pending")
        time.sleep(poll_interval)
    raise TimeoutError(f"Upload not completed within {timeout}s")


def add_assets_to_creative_sets(asset_ids: list[str],
                                 creative_set_ids: list[str]) -> dict:
    """Add assets to creative sets (max 10 assets, 50 creative sets)."""
    body = {"asset_ids": asset_ids, "creative_set_ids": creative_set_ids}
    return _request("POST", "asset/add-to-creative-sets", json_body=body)


def remove_assets_from_creative_sets(asset_id: str,
                                      creative_set_ids: list[str]) -> dict:
    """Remove an asset from creative sets (max 50)."""
    body = {"asset_id": asset_id, "creative_set_ids": creative_set_ids}
    return _request("POST", "asset/remove-from-creative-sets", json_body=body)


def remove_assets_from_all_creative_sets(asset_ids: list[str]) -> dict:
    """Remove assets from all creative sets (max 10)."""
    body = {"asset_ids": asset_ids}
    return _request("POST", "asset/remove-from-all-creative-sets", json_body=body)


# ──────────────────────────────────────────────
# Convenience / Bulk Operations
# ──────────────────────────────────────────────

def bulk_upload_and_create_set(name: str, file_paths: list[str],
                                campaign_id: Optional[str] = None,
                                languages: Optional[list[str]] = None,
                                countries: Optional[list[str]] = None) -> dict:
    """Upload files, wait for processing, create a creative set with the results.

    Returns dict with upload_result and creative_set.
    """
    print(f"Uploading {len(file_paths)} files...")
    upload_result = upload_assets(file_paths)
    upload_id = upload_result.get("upload_id")

    print(f"Upload started (ID: {upload_id}). Waiting for processing...")
    final_result = wait_for_upload(upload_id)

    # Collect successful asset IDs
    details = final_result.get("details", [])
    successful_assets = [
        {"id": d["id"]} for d in details if d.get("status") == "SUCCESS"
    ]
    failed = [d for d in details if d.get("status") == "FAILURE"]

    if failed:
        print(f"Warning: {len(failed)} files failed to upload:")
        for f in failed:
            print(f"  - {f.get('name')}: {f.get('error', 'unknown error')}")

    if not successful_assets:
        raise Exception("No files were successfully uploaded")

    print(f"Creating creative set '{name}' with {len(successful_assets)} assets...")
    creative_set = create_creative_set(
        name=name,
        assets=successful_assets,
        campaign_id=campaign_id,
        languages=languages,
        countries=countries,
    )

    return {
        "upload_result": final_result,
        "creative_set": creative_set,
        "successful_count": len(successful_assets),
        "failed_count": len(failed),
    }


def exclude_countries_from_campaign(campaign_id: int,
                                    countries_to_exclude: list[str]) -> dict:
    """Exclude countries by rebuilding the targeting list without them.

    Since the API only supports inclusion-based targeting, this:
    1. Fetches the campaign's current targeting
    2. Removes the specified countries
    3. Updates the campaign with the new list
    """
    campaigns = list_campaigns(ids=[campaign_id])
    campaign_list = campaigns if isinstance(campaigns, list) else campaigns.get("campaigns", campaigns.get("data", []))
    if not campaign_list:
        raise Exception(f"Campaign {campaign_id} not found")

    campaign = campaign_list[0]
    current_targeting = campaign.get("targeting", [])
    exclude_set = {c.upper() for c in countries_to_exclude}

    new_targeting = [
        t for t in current_targeting
        if t.get("country_code", "").upper() not in exclude_set
    ]

    removed = len(current_targeting) - len(new_targeting)
    if removed == 0:
        print(f"None of {countries_to_exclude} were in the campaign targeting")
        return campaign

    print(f"Removing {removed} countries from targeting: {countries_to_exclude}")
    return update_campaign(campaign_id, targeting=new_targeting)


def duplicate_creative_set_to_campaigns(creative_set_id: str,
                                         campaign_ids: list[str],
                                         status: str = "LIVE") -> list[dict]:
    """Clone a creative set to multiple campaigns."""
    results = []
    for cid in campaign_ids:
        result = clone_creative_set(
            campaign_id=cid,
            creative_set_id=creative_set_id,
            status=status,
        )
        results.append(result)
        print(f"Cloned creative set {creative_set_id} to campaign {cid}")
    return results


def bulk_pause_creative_sets(creative_set_ids: list[str]) -> list[dict]:
    """Pause multiple creative sets at once."""
    results = []
    for csid in creative_set_ids:
        result = pause_creative_set(csid)
        results.append(result)
        print(f"Paused creative set {csid}")
    return results


def bulk_resume_creative_sets(creative_set_ids: list[str]) -> list[dict]:
    """Resume multiple creative sets at once."""
    results = []
    for csid in creative_set_ids:
        result = resume_creative_set(csid)
        results.append(result)
        print(f"Resumed creative set {csid}")
    return results


if __name__ == "__main__":
    # Quick connection test
    print("Testing Axon API connection...")
    try:
        campaigns = list_campaigns(page=1, size=5)
        print(f"Connection successful!")
        print(json.dumps(campaigns, indent=2, default=str)[:2000])
    except Exception as e:
        print(f"Connection failed: {e}")
