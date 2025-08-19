"""
CSV/XLSX parsing utilities for packing management
"""
import io
import pandas as pd
from typing import Dict, List, Tuple, Optional
import re

def normalize_column_name(name: str) -> str:
    """Normalize column name for matching"""
    if not name:
        return ""
    return re.sub(r'[_\s]+', '_', name.lower().strip())

def detect_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    """
    Auto-detect important columns from a list of column names.
    Returns a dict mapping column type to actual column name.
    """
    normalized_cols = {normalize_column_name(col): col for col in columns}
    
    # Column detection patterns
    patterns = {
        'order_col': ['order', 'order_number', 'name', 'order no', 'order#', 'order_id'],
        'product_col': ['product', 'title', 'product_name', 'lineitem name', 'item_name'],
        'variant_col': ['variant', 'sku_variant', 'option', 'sku', 'lineitem variant title'],
        'color_col': ['color', 'colour'],
        'main_photo_col': ['main_photo', 'main_photo_url', 'photo', 'image', 'image_url', 'main photo link'],
        'polaroid_count_col': ['polaroid', 'polaroids', 'polaroid_count', 'polaroid link'],
        'status_col': ['status', 'photo_status', 'packing_status', 'main photo status'],
        'engrave_type_col': ['back_engraving_type', 'engraving_type', 'engrave_type', 'back engraving type'],
        'engrave_msg_col': ['back_engraving', 'engraving', 'message', 'back engraving value']
    }
    
    detected = {}
    for col_type, candidates in patterns.items():
        detected[col_type] = None
        for candidate in candidates:
            if candidate in normalized_cols:
                detected[col_type] = normalized_cols[candidate]
                break
    
    return detected

def parse_file_content(file_content: bytes, filename: str, max_rows: int = 2000) -> Tuple[List[str], List[Dict], Dict]:
    """
    Parse CSV/XLSX file content and return columns, rows, and detected column mapping.
    
    Args:
        file_content: Raw file bytes
        filename: Original filename for extension detection
        max_rows: Maximum rows to parse for preview
        
    Returns:
        Tuple of (columns, rows, detected_columns)
    """
    try:
        # Determine file type and parse
        if filename.lower().endswith('.csv'):
            # Try different encodings
            for encoding in ['utf-8', 'utf-8-sig', 'latin-1']:
                try:
                    df = pd.read_csv(
                        io.BytesIO(file_content), 
                        encoding=encoding,
                        dtype=str, 
                        keep_default_na=False,
                        nrows=max_rows
                    )
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Could not decode CSV file with any supported encoding")
                
        elif filename.lower().endswith(('.xls', '.xlsx')):
            df = pd.read_excel(
                io.BytesIO(file_content), 
                dtype=str,
                nrows=max_rows
            ).fillna("")
        else:
            raise ValueError("Unsupported file type. Please use CSV or XLSX.")
        
        # Get columns and normalize
        columns = [str(col).strip() for col in df.columns]
        
        # Detect important columns
        detected = detect_columns(columns)
        
        # Convert to rows
        rows = []
        for _, row in df.iterrows():
            row_dict = {}
            for col in columns:
                value = row.get(col, "")
                # Convert to string and handle NaN
                if pd.isna(value):
                    value = ""
                row_dict[col] = str(value).strip()
            rows.append(row_dict)
        
        return columns, rows, detected
        
    except Exception as e:
        raise ValueError(f"Failed to parse file: {str(e)}")

def is_valid_url(url: str) -> bool:
    """Check if a string looks like a valid URL"""
    if not url or url.lower() in ['na', 'n/a', 'null', 'none', '']:
        return False
    return url.startswith(('http://', 'https://', '//'))

def get_status_heuristics(row: Dict, detected: Dict) -> Dict[str, str]:
    """
    Apply heuristics to determine status badges for a row.
    
    Returns:
        Dict with status information for display
    """
    status_info = {
        'main_photo_status': 'OK',
        'polaroid_status': 'OK',
        'overall_status': 'OK'
    }
    
    # Check main photo status
    main_photo_col = detected.get('main_photo_col')
    if main_photo_col and main_photo_col in row:
        photo_value = row[main_photo_col]
        if not is_valid_url(photo_value):
            status_info['main_photo_status'] = 'Missing photo'
            status_info['overall_status'] = 'Missing photo'
    
    # Check polaroid status
    polaroid_col = detected.get('polaroid_count_col')
    if polaroid_col and polaroid_col in row:
        polaroid_value = row[polaroid_col]
        try:
            count = int(polaroid_value) if polaroid_value else 0
            if count == 0:
                status_info['polaroid_status'] = 'Missing'
                if status_info['overall_status'] == 'OK':
                    status_info['overall_status'] = 'Missing polaroid'
        except (ValueError, TypeError):
            if not polaroid_value or polaroid_value.lower() in ['na', 'n/a', 'null', 'none', '']:
                status_info['polaroid_status'] = 'Missing'
                if status_info['overall_status'] == 'OK':
                    status_info['overall_status'] = 'Missing polaroid'
    
    return status_info
