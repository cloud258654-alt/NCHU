from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def get_token() -> str:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        print("Error: LINE_CHANNEL_ACCESS_TOKEN is not configured in .env", file=sys.stderr)
        sys.exit(1)
    return token


def get_liff_id() -> str:
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id:
        print("Warning: LINE_LIFF_ID is not configured in .env. Action URIs using LIFF will not point to a valid LIFF ID.", file=sys.stderr)
    return liff_id


def get_dashboard_url() -> str:
    url = os.getenv("BI_RMP_DASHBOARD_URL", "").strip()
    if not url:
        url = "https://example.com/dashboard"
    return url


def make_request(url: str, method: str, headers: dict[str, str], data: bytes | None = None) -> dict[str, any] | bytes:
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = resp.read()
            if resp.info().get_content_type() == "application/json":
                return json.loads(resp_data.decode("utf-8"))
            return resp_data
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        print(f"Response body: {err_body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)


def create_rich_menu() -> str:
    token = get_token()
    dashboard_url = get_dashboard_url()
    
    # Compact 3-column layout (2500x843)
    rich_menu_data = {
        "size": {
            "width": 2500,
            "height": 843
        },
        "selected": True,
        "name": "BI-RMP Compact Menu",
        "chatBarText": "開啟選單",
        "areas": [
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 833,
                    "height": 843
                },
                "action": {
                    "type": "message",
                    "label": "風評查詢",
                    "text": "風評查詢"
                }
            },
            {
                "bounds": {
                    "x": 833,
                    "y": 0,
                    "width": 834,
                    "height": 843
                },
                "action": {
                    "type": "uri",
                    "label": "輿情中心",
                    "uri": dashboard_url
                }
            },
            {
                "bounds": {
                    "x": 1667,
                    "y": 0,
                    "width": 833,
                    "height": 843
                },
                "action": {
                    "type": "message",
                    "label": "功能規劃中",
                    "text": "功能規劃中"
                }
            }
        ]
    }
    
    url = "https://api.line.me/v2/bot/richmenu"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print("Creating rich menu...")
    resp = make_request(url, "POST", headers, json.dumps(rich_menu_data).encode("utf-8"))
    rich_menu_id = resp.get("richMenuId")
    print(f"Rich Menu created successfully. ID: {rich_menu_id}")
    return rich_menu_id


def upload_image(rich_menu_id: str, image_path: str) -> None:
    token = get_token()
    img_path = Path(image_path)
    if not img_path.exists():
        print(f"Error: Image path {image_path} does not exist.", file=sys.stderr)
        sys.exit(1)
        
    # Detect content type
    suffix = img_path.suffix.lower()
    if suffix in (".png",):
        content_type = "image/png"
    elif suffix in (".jpg", ".jpeg"):
        content_type = "image/jpeg"
    else:
        print(f"Error: Image must be PNG or JPEG. Got suffix: {suffix}", file=sys.stderr)
        sys.exit(1)
        
    url = f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type
    }
    
    print(f"Uploading image {image_path} to Rich Menu {rich_menu_id}...")
    image_data = img_path.read_bytes()
    make_request(url, "POST", headers, image_data)
    print("Image uploaded successfully.")


def set_default(rich_menu_id: str) -> None:
    token = get_token()
    url = f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    print(f"Setting Rich Menu {rich_menu_id} as default...")
    make_request(url, "POST", headers)
    print("Set default rich menu successfully.")


def list_rich_menus() -> None:
    token = get_token()
    url = "https://api.line.me/v2/bot/richmenu/list"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    print("Listing rich menus...")
    resp = make_request(url, "GET", headers)
    menus = resp.get("richmenus", [])
    if not menus:
        print("No rich menus found.")
        return
        
    # Get current default rich menu
    default_id = get_default_rich_menu_id()
    
    print(f"Found {len(menus)} rich menus:")
    for menu in menus:
        mid = menu.get("richMenuId")
        name = menu.get("name")
        chat_bar = menu.get("chatBarText")
        is_default = " (DEFAULT)" if mid == default_id else ""
        print(f"- ID: {mid} | Name: {name} | Chat Bar: {chat_bar}{is_default}")


def get_default_rich_menu_id() -> str | None:
    token = get_token()
    url = "https://api.line.me/v2/bot/user/all/richmenu"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    try:
        resp = make_request(url, "GET", headers)
        if isinstance(resp, dict):
            return resp.get("richMenuId")
    except SystemExit:
        pass
    return None


def cancel_default() -> None:
    token = get_token()
    url = "https://api.line.me/v2/bot/user/all/richmenu"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    print("Canceling default rich menu...")
    make_request(url, "DELETE", headers)
    print("Canceled default rich menu successfully.")


def delete_rich_menu(rich_menu_id: str) -> None:
    token = get_token()
    url = f"https://api.line.me/v2/bot/richmenu/{rich_menu_id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    print(f"Deleting rich menu {rich_menu_id}...")
    make_request(url, "DELETE", headers)
    print("Deleted rich menu successfully.")


def print_help() -> None:
    print("""
LINE Rich Menu Manager Utility
Usage:
  python Backend/scripts/manage_rich_menu.py create
  python Backend/scripts/manage_rich_menu.py upload <rich_menu_id> <image_path>
  python Backend/scripts/manage_rich_menu.py set-default <rich_menu_id>
  python Backend/scripts/manage_rich_menu.py cancel-default
  python Backend/scripts/manage_rich_menu.py list
  python Backend/scripts/manage_rich_menu.py delete <rich_menu_id>
  python Backend/scripts/manage_rich_menu.py quick-setup <image_path>
""")


def main() -> None:
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    if cmd == "create":
        create_rich_menu()
    elif cmd == "upload":
        if len(sys.argv) < 4:
            print("Usage: python Backend/scripts/manage_rich_menu.py upload <rich_menu_id> <image_path>", file=sys.stderr)
            sys.exit(1)
        upload_image(sys.argv[2], sys.argv[3])
    elif cmd == "set-default":
        if len(sys.argv) < 3:
            print("Usage: python Backend/scripts/manage_rich_menu.py set-default <rich_menu_id>", file=sys.stderr)
            sys.exit(1)
        set_default(sys.argv[2])
    elif cmd == "cancel-default":
        cancel_default()
    elif cmd == "list":
        list_rich_menus()
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: python Backend/scripts/manage_rich_menu.py delete <rich_menu_id>", file=sys.stderr)
            sys.exit(1)
        delete_rich_menu(sys.argv[2])
    elif cmd == "quick-setup":
        if len(sys.argv) < 3:
            print("Usage: python Backend/scripts/manage_rich_menu.py quick-setup <image_path>", file=sys.stderr)
            sys.exit(1)
        image_path = sys.argv[2]
        rich_menu_id = create_rich_menu()
        upload_image(rich_menu_id, image_path)
        set_default(rich_menu_id)
        print("\nQuick setup completed! Your Rich Menu is now active.")
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
