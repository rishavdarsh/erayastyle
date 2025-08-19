"""
Orders service for managing order processing, Shopify integration, and core business logic
"""
import os
import requests
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import io
import zipfile
import tempfile

from app.services import supa

# Shopify configuration
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
SHOPIFY_VERSION = "2024-01"  # Latest stable version

class ShopifyOrderService:
    """Service for managing Shopify order operations"""
    
    def __init__(self):
        self.base_url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_VERSION}"
        self.headers = {
            "X-Shopify-Access-Token": SHOPIFY_TOKEN,
            "Content-Type": "application/json"
        }
    
    def _shopify_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make a request to Shopify API"""
        if not SHOPIFY_SHOP or not SHOPIFY_TOKEN:
            raise Exception("Shopify configuration not set. Please set SHOPIFY_SHOP and SHOPIFY_TOKEN environment variables.")
        
        url = f"{self.base_url}/{endpoint}"
        response = requests.get(url, headers=self.headers, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Shopify API error: {response.status_code} - {response.text}")
        
        return response.json()
    
    def fetch_orders(
        self, 
        status: str = "any",
        fulfillment_status: str = None,
        limit: int = 100,
        page_info: str = None,
        created_at_min: str = None,
        created_at_max: str = None
    ) -> Dict[str, Any]:
        """Fetch orders from Shopify with pagination support"""
        try:
            params = {
                "limit": min(limit, 250),  # Shopify max is 250
                "status": status,
                "fields": "id,name,order_number,created_at,financial_status,fulfillment_status,customer,email,order_status_url,line_items"
            }
            
            # Add optional parameters
            if fulfillment_status:
                params["fulfillment_status"] = fulfillment_status
            if page_info:
                params["page_info"] = page_info
            if created_at_min:
                params["created_at_min"] = created_at_min
            if created_at_max:
                params["created_at_max"] = created_at_max
                
            # Call Shopify API
            data = self._shopify_request("orders.json", params)
            
            return {
                "orders": data.get("orders", []),
                "next_page_info": data.get("_pagination", {}).get("next_page_info"),
                "prev_page_info": data.get("_pagination", {}).get("prev_page_info")
            }
            
        except Exception as e:
            raise Exception(f"Error fetching Shopify orders: {str(e)}")
    
    def fetch_all_orders(
        self, 
        status: str = "any",
        fulfillment_status: str = None,
        created_at_min: str = None,
        created_at_max: str = None
    ) -> List[Dict]:
        """Fetch all orders from Shopify (handles pagination automatically)"""
        try:
            all_orders = []
            page_info = None
            
            while True:
                result = self.fetch_orders(
                    status=status,
                    fulfillment_status=fulfillment_status,
                    limit=250,  # Maximum allowed
                    page_info=page_info,
                    created_at_min=created_at_min,
                    created_at_max=created_at_max
                )
                
                all_orders.extend(result["orders"])
                
                # Check if there are more pages
                if not result["next_page_info"]:
                    break
                    
                page_info = result["next_page_info"]
            
            return all_orders
            
        except Exception as e:
            raise Exception(f"Error fetching all Shopify orders: {str(e)}")
    
    def convert_orders_to_rows(self, orders: List[Dict]) -> List[Dict]:
        """Convert Shopify orders to standardized row format"""
        converted = []
        
        for order in orders:
            line_items = order.get("line_items", [])
            
            for item in line_items:
                properties = {}
                
                # Parse line item properties
                if item.get("properties") and isinstance(item["properties"], list):
                    for prop in item["properties"]:
                        if prop.get("name") and prop.get("value"):
                            properties[prop["name"].lower()] = prop["value"]
                
                # Extract data according to mapping rules
                main_photo = properties.get('photo') or properties.get('photo link') or ''
                polaroid_str = properties.get('polaroid') or properties.get('your polaroid image') or ''
                polaroids = []
                
                if polaroid_str:
                    polaroids = [p.strip() for p in polaroid_str.split(',') if p.strip()]
                
                back_value = properties.get('back message') or properties.get('back engraving') or ''
                
                row = {
                    'order_id': order.get('id'),
                    'order_number': order.get('name') or f"#{order.get('order_number') or order.get('id')}",
                    'product_name': item.get('name') or '',
                    'variant': item.get('variant_title') or '',
                    'color': '',  # Leave empty as requested
                    'main_photo': main_photo,
                    'polaroids': polaroids,
                    'back_engraving_type': 'Back Message' if back_value else '',
                    'back_engraving_value': back_value,
                    'main_photo_status': 'Success' if main_photo else '',
                    'polaroid_count': len(polaroids),
                    'fulfillment_status': order.get('fulfillment_status') or 'unfulfilled',
                    'financial_status': order.get('financial_status') or 'pending',
                    'customer_email': order.get('customer', {}).get('email', ''),
                    'created_at': order.get('created_at', ''),
                    'line_item_id': item.get('id')
                }
                
                converted.append(row)
        
        return converted

class OrderProcessingService:
    """Service for processing order data and files"""
    
    def __init__(self):
        self.shopify_service = ShopifyOrderService()
    
    def process_csv_file(self, file_path: Path, options: Dict = None) -> Dict[str, Any]:
        """Process CSV file and extract order information"""
        try:
            # Read CSV file
            df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
            
            # Process the data
            processed_data = self._process_dataframe(df, options or {})
            
            return {
                "success": True,
                "data": processed_data,
                "total_rows": len(processed_data),
                "file_path": str(file_path)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "file_path": str(file_path)
            }
    
    def _process_dataframe(self, df: pd.DataFrame, options: Dict) -> List[Dict]:
        """Process DataFrame and extract order information"""
        processed_rows = []
        
        # Normalize column names
        cols = {c.strip(): c for c in df.columns}
        
        def get_col(name: str, fallback: str = None):
            return cols.get(name) or cols.get(fallback) or name
        
        for _, row in df.iterrows():
            # Extract data from row
            order_data = {
                'order_number': row.get(get_col('Order Number', 'Order Name'), ''),
                'product_name': row.get(get_col('Product Name', 'Lineitem Name'), ''),
                'variant': row.get(get_col('Variant', 'Lineitem Variant Title'), ''),
                'color': '',  # Leave empty as requested
                'main_photo': row.get(get_col('Main Photo Link'), ''),
                'polaroids_raw': row.get(get_col('Polaroid Link(s)'), ''),
                'back_engraving_type': row.get(get_col('Back Engraving Type'), ''),
                'back_engraving_value': row.get(get_col('Back Engraving Value'), ''),
                'main_photo_status': row.get(get_col('Main Photo Status'), ''),
                'polaroid_count': row.get(get_col('Polaroid Count'), '0')
            }
            
            # Process polaroids
            polaroid_str = order_data['polaroids_raw']
            if polaroid_str:
                polaroids = [p.strip() for p in str(polaroid_str).split(',') if p.strip()]
                order_data['polaroids'] = polaroids
                order_data['polaroid_count'] = str(len(polaroids))
            else:
                order_data['polaroids'] = []
                order_data['polaroid_count'] = '0'
            
            # Clean up data
            for key, value in order_data.items():
                if isinstance(value, str):
                    order_data[key] = value.strip()
            
            processed_rows.append(order_data)
        
        return processed_rows
    
    def extract_color_from_image(self, image_url: str) -> str:
        """Extract color information from an image (placeholder for now)"""
        # TODO: Implement actual color extraction logic
        # This could use image processing libraries like PIL, OpenCV, or cloud services
        return "Unknown"
    
    def create_orders_export(
        self, 
        orders: List[Dict], 
        export_format: str = "csv",
        include_photos: bool = False
    ) -> Tuple[bytes, str]:
        """Create export file from orders data"""
        try:
            if export_format.lower() == "csv":
                return self._create_csv_export(orders), "orders_export.csv"
            elif export_format.lower() == "excel":
                return self._create_excel_export(orders), "orders_export.xlsx"
            else:
                raise ValueError(f"Unsupported export format: {export_format}")
                
        except Exception as e:
            raise Exception(f"Error creating export: {str(e)}")
    
    def _create_csv_export(self, orders: List[Dict]) -> bytes:
        """Create CSV export"""
        if not orders:
            return b""
        
        # Convert to DataFrame
        df = pd.DataFrame(orders)
        
        # Convert to CSV bytes
        output = io.StringIO()
        df.to_csv(output, index=False)
        return output.getvalue().encode('utf-8')
    
    def _create_excel_export(self, orders: List[Dict]) -> bytes:
        """Create Excel export"""
        if not orders:
            return b""
        
        # Convert to DataFrame
        df = pd.DataFrame(orders)
        
        # Convert to Excel bytes
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Orders')
        
        return output.getvalue()

class OrderDownloadService:
    """Service for downloading order photos and polaroids"""
    
    def __init__(self):
        self.download_dir = Path("downloads/orders")
        self.download_dir.mkdir(parents=True, exist_ok=True)
    
    def download_order_photos(
        self, 
        orders: List[Dict], 
        include_main: bool = True,
        include_polaroids: bool = True
    ) -> Path:
        """Download photos for specified orders and create ZIP file"""
        try:
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Create ZIP file
                zip_path = self.download_dir / f"order_photos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                
                with zipfile.ZipFile(zip_path, 'w') as zip_file:
                    for order in orders:
                        order_dir = temp_path / str(order.get('order_number', 'unknown'))
                        order_dir.mkdir(exist_ok=True)
                        
                        # Download main photo
                        if include_main and order.get('main_photo'):
                            try:
                                main_photo_path = self._download_image(
                                    order['main_photo'], 
                                    order_dir / "main_photo.jpg"
                                )
                                if main_photo_path:
                                    zip_file.write(main_photo_path, f"{order['order_number']}/main_photo.jpg")
                            except Exception as e:
                                print(f"Error downloading main photo for {order['order_number']}: {e}")
                        
                        # Download polaroids
                        if include_polaroids and order.get('polaroids'):
                            for i, polaroid_url in enumerate(order['polaroids']):
                                try:
                                    polaroid_path = self._download_image(
                                        polaroid_url, 
                                        order_dir / f"polaroid_{i+1}.jpg"
                                    )
                                    if polaroid_path:
                                        zip_file.write(polaroid_path, f"{order['order_number']}/polaroid_{i+1}.jpg")
                                except Exception as e:
                                    print(f"Error downloading polaroid {i+1} for {order['order_number']}: {e}")
                
                return zip_path
                
        except Exception as e:
            raise Exception(f"Error creating photo download: {str(e)}")
    
    def _download_image(self, url: str, local_path: Path) -> Optional[Path]:
        """Download an image from URL to local path"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            return local_path
            
        except Exception as e:
            print(f"Error downloading image from {url}: {e}")
            return None

# Global service instances
shopify_service = ShopifyOrderService()
order_processing_service = OrderProcessingService()
order_download_service = OrderDownloadService()
