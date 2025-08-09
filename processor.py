# processor.py
import os
import re
import json
import pytz
import unicodedata
import zipfile
import multiprocessing
from io import BytesIO
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pandas as pd
import requests
from PIL import Image
from html2image import Html2Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ------------------ Global locks & counters ------------------
skipped_lock = Lock()
backmsg_lock = Lock()
counter_lock = Lock()

counters = {"success_main": 0, "success_polaroid": 0}

# ------------------ Feature toggles (safe defaults) ------------------
# If you haven't installed wkhtmltoimage (wkhtmltopdf), keep this False.
# When set True, we will render back message PNGs.
DEFAULT_GENERATE_BACK_MESSAGE_IMAGES = False

# ------------------ Helpers ------------------
def safe_filename(name: str, maxlen: int = 180) -> str:
    name = str(name)
    name = re.sub(r"[^\w\s\-\(\)\[\]#&\.]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace(" ", "_")
    return name[:maxlen]

def remove_emojis(text: str) -> str:
    if text is None:
        return ""
    cleaned = ''.join(ch for ch in text if not unicodedata.category(ch).startswith(('C', 'S')))
    cleaned = re.sub(r'[â¤ï¸®©™ ¶«»]', '', cleaned)
    cleaned = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', cleaned)
    return cleaned.strip()

def extract_color(variant: str) -> str:
    if not variant or str(variant).strip().lower() == "nan":
        return "Unknown"
    v = str(variant).lower()
    colors = ["rose gold", "gold", "silver", "black", "steel"]
    for c in colors:
        if c in v:
            return c.title()
    if "/" in variant:
        return variant.split("/")[0].strip().title()
    return variant.split()[0].strip().title()

def parse_lineitem_properties(props_raw):
    if props_raw is None or (isinstance(props_raw, float) and pd.isna(props_raw)):
        return []
    s = str(props_raw).strip()
    s = s.replace("''", '"').replace("u'", '"').replace("None", "null")
    try:
        return json.loads(s)
    except Exception:
        try:
            return json.loads(s.strip('"'))
        except Exception:
            return []

def clean_text(text):
    return "" if text is None or (isinstance(text, float) and pd.isna(text)) else str(text).strip()

def make_session(retry_total: int, backoff_factor: float) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retry_total,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def download_and_save_png(session: requests.Session, img_url: str, save_path: str, timeout: int) -> bool:
    try:
        resp = session.get(img_url, timeout=timeout)
        resp.raise_for_status()
        with Image.open(BytesIO(resp.content)).convert("RGB") as img:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            img.save(save_path, "PNG")
        return True
    except Exception:
        return False

def generate_back_message_image(order_id, message_text, save_path, width=709, height=189):
    """
    Requires wkhtmltoimage to be installed (via wkhtmltopdf).
    If it's not installed, this may fail; we gate this with a toggle above.
    """
    cleaned_text = remove_emojis(message_text).upper()
    temp_height = max(height, 300)
    hti = Html2Image(output_path=os.path.dirname(save_path))
    temp_name = os.path.basename(save_path).replace(".png", "_temp.png")

    html = f"""
    <html>
    <head>
    <style>
        body {{
            width: {width}px;
            height: {temp_height}px;
            display: flex;
            justify-content: center;
            align-items: center;
            background-color: white;
            font-size: 28px;
            font-family: Arial, sans-serif;
            text-align: center;
            line-height: 1.2;
            padding: 0 10px;
            margin: 0;
        }}
        span {{
            max-width: {width - 40}px;
            word-break: break-word;
            white-space: pre-wrap;
        }}
    </style>
    </head>
    <body><span>{cleaned_text}</span></body>
    </html>
    """

    # Render to a taller temporary image, then crop to target height
    hti.screenshot(html_str=html, save_as=temp_name, size=(width, temp_height))
    temp_path = os.path.join(os.path.dirname(save_path), temp_name)
    with Image.open(temp_path) as img:
        top = max((temp_height - height) // 2, 0)
        cropped = img.crop((0, top, width, top + height))
        cropped.save(save_path)
    try:
        os.remove(temp_path)
    except Exception:
        pass
    return True

# ------------------ Main worker ------------------
def process_csv_file(csv_path: Path, out_dir: Path, status_cb=lambda s, progress=None: None, options: dict | None = None) -> Path:
    """
    csv_path: path to uploaded CSV
    out_dir: job working directory
    status_cb: callback(str, progress_float)
    options:
        - order_prefix (str) default "#ER"
        - max_threads (int) default 8
        - retry_total (int) default 3
        - backoff_factor (float) default 0.6
        - timeout_sec (int) default 15
        - include_per_product_csv (bool) default True
        - include_back_messages_csv (bool) default True
        - zip_name (str) default "results"
        - generate_back_message_images (bool) default DEFAULT_GENERATE_BACK_MESSAGE_IMAGES
    Returns: path to ZIP file with all outputs
    """
    # -------- Options & setup --------
    opts = options or {}
    order_prefix = opts.get("order_prefix", "#ER")
    max_threads = int(opts.get("max_threads", 8))
    retry_total = int(opts.get("retry_total", 3))
    backoff_factor = float(opts.get("backoff_factor", 0.6))
    timeout_sec = int(opts.get("timeout_sec", 15))
    include_per_product_csv = bool(opts.get("include_per_product_csv", True))
    include_back_messages_csv = bool(opts.get("include_back_messages_csv", True))
    zip_name = str(opts.get("zip_name", "results")).strip() or "results"
    generate_back_images = bool(opts.get("generate_back_message_images", DEFAULT_GENERATE_BACK_MESSAGE_IMAGES))

    session = make_session(retry_total, backoff_factor)

    status_cb("Reading CSV...", 5.0)
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df.columns = df.columns.str.strip()

    required_cols = ["Order Name", "Lineitem Properties", "Lineitem Name", "Lineitem Variant Title"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"Missing columns: {missing}")

    # Filter by prefix
    status_cb("Filtering orders...", 8.0)
    df = df[df["Order Name"].astype(str).str.startswith(order_prefix)].copy()

    # Build orders list
    status_cb("Parsing orders...", 12.0)
    orders: list[dict] = []
    skipped_images: list[dict] = []

    for order_id in df["Order Name"].unique():
        order_rows = df[df["Order Name"] == order_id]
        photo_link, polaroid_links, product_name, variant = "", [], "", ""
        back_message, spotify_link = "", ""

        for _, row in order_rows.iterrows():
            props = parse_lineitem_properties(row.get("Lineitem Properties", ""))

            for item in props:
                key = clean_text(item.get("name", "")).lower()
                val = clean_text(item.get("value", ""))

                if key in ["photo", "photo link"]:
                    photo_link = val
                    product_name = clean_text(row.get("Lineitem Name", "")).title()
                    variant = clean_text(row.get("Lineitem Variant Title", "")).title()

                elif key in ["polaroid", "your polaroid image"]:
                    if val:
                        polaroid_links.append(val)

                elif "back message" in key:
                    back_message = val

                elif "spotify" in key or "music" in key:
                    spotify_link = val

        orders.append({
            "Order Number": order_id,
            "Product Name": product_name,
            "Variant": variant,
            "Main Photo Link": photo_link,
            "Polaroid Link(s)": polaroid_links[:],
            "Back Engraving Type": "Back Message" if back_message else ("Spotify Link" if spotify_link else ""),
            "Back Engraving Value": back_message or spotify_link,
            "Main Photo Status": "",
            "Polaroid Count": 0
        })

    output_folder = out_dir / "converted_images"
    output_folder.mkdir(parents=True, exist_ok=True)

    # Group by product
    product_groups: dict[str, list[dict]] = defaultdict(list)
    for order in orders:
        key = re.sub(r"[^\w\s-]", "", order["Product Name"] or "Unknown").strip().title().replace(" ", "_") or "Unknown"
        product_groups[key].append(order)

    # Clamp threads
    max_threads = max(1, min(max_threads, multiprocessing.cpu_count() * 2))

    # Process each product group
    total_products = len(product_groups)
    processed_products = 0

    for product_name, group_orders in product_groups.items():
        processed_products += 1
        status_cb(f"Processing product {processed_products}/{total_products}: {product_name}",
                  15.0 + 70.0 * processed_products / max(1, total_products))

        main_dir = output_folder / product_name / "main"
        polaroid_dir = output_folder / product_name / "polaroids"
        back_dir = output_folder / product_name / "back_messages"
        main_dir.mkdir(parents=True, exist_ok=True)
        polaroid_dir.mkdir(parents=True, exist_ok=True)
        back_dir.mkdir(parents=True, exist_ok=True)

        back_messages_rows: list[dict] = []

        def process_one(order: dict):
            order_id = order["Order Number"]
            variant = clean_text(order["Variant"]).title()
            color = extract_color(variant)
            photo_link = clean_text(order["Main Photo Link"])
            polaroid_list = order.get("Polaroid Link(s)", []) or []
            back_value = order["Back Engraving Value"]

            # MAIN
            main_fname = safe_filename(f"{order_id} -{color}.png")
            main_path = main_dir / main_fname
            if photo_link.lower().startswith("http"):
                if download_and_save_png(session, photo_link, str(main_path), timeout_sec):
                    order["Main Photo Status"] = "✅ Success"
                    with counter_lock:
                        counters["success_main"] += 1
                else:
                    order["Main Photo Status"] = "❌ Failed"
                    with skipped_lock:
                        skipped_images.append({"Order ID": order_id, "Type": "Main Photo", "Link": photo_link})
            else:
                order["Main Photo Status"] = "⚠️ Invalid"
                with skipped_lock:
                    skipped_images.append({"Order ID": order_id, "Type": "Main Photo", "Link": photo_link})

            # POLAROID(S)
            count = 0
            for idx, link in enumerate(polaroid_list, 1):
                if isinstance(link, str) and link.lower().startswith("http"):
                    p_fname = safe_filename(f"{order_id} -{color}_polaroid_{idx}.png")
                    p_path = polaroid_dir / p_fname
                    if download_and_save_png(session, link, str(p_path), timeout_sec):
                        count += 1
                        with counter_lock:
                            counters["success_polaroid"] += 1
                    else:
                        with skipped_lock:
                            skipped_images.append({"Order ID": order_id, "Type": f"Polaroid {idx}", "Link": link})
                else:
                    with skipped_lock:
                        skipped_images.append({"Order ID": order_id, "Type": f"Polaroid {idx}", "Link": link})
            order["Polaroid Count"] = count

            # BACK MESSAGE (toggleable)
            if back_value and generate_back_images:
                try:
                    b_fname = safe_filename(f"{order_id} -{color}_backmsg.png")
                    b_path = back_dir / b_fname
                    generate_back_message_image(order_id, back_value, str(b_path))
                    with backmsg_lock:
                        back_messages_rows.append({
                            "Order ID": order_id,
                            "Engraving Type": order["Back Engraving Type"],
                            "Engraving Value": remove_emojis(back_value).upper()
                        })
                except Exception:
                    # Don't fail the whole job for one bad render
                    pass
            else:
                # We may still want the CSV row even if image is disabled, depending on option below
                if back_value:
                    with backmsg_lock:
                        back_messages_rows.append({
                            "Order ID": order_id,
                            "Engraving Type": order["Back Engraving Type"],
                            "Engraving Value": remove_emojis(back_value).upper()
                        })

        with ThreadPoolExecutor(max_workers=max_threads) as pool:
            list(pool.map(process_one, group_orders))

        # Per-product CSV
        if include_per_product_csv:
            rows = []
            for o in group_orders:
                pls = o.get("Polaroid Link(s)", [])
                pls_str = ", ".join(pls) if isinstance(pls, list) else str(pls)
                rows.append({
                    "Order Number": o["Order Number"],
                    "Product Name": o["Product Name"],
                    "Variant": o["Variant"],
                    "Main Photo Link": o["Main Photo Link"],
                    "Polaroid Link(s)": pls_str,
                    "Back Engraving Type": o.get("Back Engraving Type", ""),
                    "Back Engraving Value": remove_emojis(o.get("Back Engraving Value", "")),
                    "Main Photo Status": o.get("Main Photo Status", "")
                })
            pd.DataFrame(rows).to_csv(
                output_folder / product_name / "Organized Orders.csv",
                index=False,
                encoding="utf-8-sig"
            )

        # Back messages CSV
        if include_back_messages_csv and back_messages_rows:
            pd.DataFrame(back_messages_rows).to_csv(
                output_folder / product_name / "Back_Messages.csv",
                index=False,
                encoding="utf-8-sig"
            )

    # Global CSVs
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    stamp = now.strftime("%d-%b-%Y_%I-%M%p")

    orders_csv = []
    for o in orders:
        ocopy = o.copy()
        pls = ocopy.get("Polaroid Link(s)", [])
        ocopy["Polaroid Link(s)"] = ", ".join(pls) if isinstance(pls, list) else str(pls)
        ocopy["Back Engraving Value"] = remove_emojis(ocopy.get("Back Engraving Value", ""))
        orders_csv.append(ocopy)

    pd.DataFrame(orders_csv).to_csv(out_dir / f"Organized Orders - {stamp}.csv", index=False, encoding="utf-8-sig")
    if 'skipped_images' in locals() and skipped_images:
        pd.DataFrame(skipped_images).to_csv(out_dir / f"Skipped_Images - {stamp}.csv", index=False, encoding="utf-8-sig")

    # Zip all outputs in this job folder
    status_cb("Creating ZIP...", 98.0)
    zip_base = zip_name.replace(" ", "_")
    zip_path = out_dir / f"{zip_base}_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in out_dir.rglob("*"):
            if p.is_file() and p != zip_path:
                z.write(p, p.relative_to(out_dir))

    status_cb("Done", 100.0)
    return zip_path
