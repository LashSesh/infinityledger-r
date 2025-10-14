"""
Triton Core - SPEC-002-konforme Normalisierung
Deterministische Payload-Normalisierung ohne Randomness.
"""

import json
from typing import Any, Dict, Union
from datetime import datetime, timedelta
import re

def normalize_payload(payload: dict) -> dict:
    """
    SPEC-002-konforme Payload-Normalisierung.
    
    Regeln:
    - Keys sortieren
    - Strings trimmen
    - Zahlen in float casten
    - Datumsstrings → ISO-8601
    - Verbotene Felder entfernen: ["debug", "tmp", "_meta"]
    
    Args:
        payload: Eingabe-Dictionary
        
    Returns:
        Normalisiertes Dictionary (deterministisch)
    """
    # Verbotene Felder entfernen
    forbidden_fields = ["debug", "tmp", "_meta"]
    
    def clean_dict(d: dict) -> dict:
        """Rekursive Bereinigung und Normalisierung."""
        cleaned = {}
        
        # Keys sortieren für Determinismus
        for key in sorted(d.keys()):
            # Verbotene Felder überspringen
            if key in forbidden_fields:
                continue
                
            value = d[key]
            
            # Rekursiv für verschachtelte Dicts
            if isinstance(value, dict):
                cleaned[key] = clean_dict(value)
            # Listen normalisieren
            elif isinstance(value, list):
                cleaned[key] = normalize_list(value)
            # Strings trimmen
            elif isinstance(value, str):
                normalized = value.strip()
                # Datumserkennung und ISO-8601 Konvertierung
                if is_date_string(normalized):
                    normalized = convert_to_iso8601(normalized)
                cleaned[key] = normalized
            # Zahlen in float casten
            elif isinstance(value, (int, float)):
                cleaned[key] = float(value)
            # Booleans beibehalten
            elif isinstance(value, bool):
                cleaned[key] = value
            # None beibehalten
            elif value is None:
                cleaned[key] = None
            else:
                # Fallback: zu String konvertieren und trimmen
                cleaned[key] = str(value).strip()
        
        return cleaned
    
    def normalize_list(lst: list) -> list:
        """Listen-Elemente normalisieren."""
        normalized = []
        for item in lst:
            if isinstance(item, dict):
                normalized.append(clean_dict(item))
            elif isinstance(item, list):
                normalized.append(normalize_list(item))
            elif isinstance(item, str):
                s = item.strip()
                if is_date_string(s):
                    s = convert_to_iso8601(s)
                normalized.append(s)
            elif isinstance(item, (int, float)):
                normalized.append(float(item))
            elif isinstance(item, bool) or item is None:
                normalized.append(item)
            else:
                normalized.append(str(item).strip())
        return normalized
    
    def is_date_string(s: str) -> bool:
        """Prüft ob String ein Datum darstellt."""
        # Einfache Heuristik für Datumserkennung
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
            r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}',  # YYYY-MM-DD HH:MM:SS
            r'^\d{2}/\d{2}/\d{4}$',  # MM/DD/YYYY oder DD/MM/YYYY
            r'^\d{2}\.\d{2}\.\d{4}$',  # DD.MM.YYYY
        ]
        return any(re.match(pattern, s) for pattern in date_patterns)
    
    def convert_to_iso8601(date_str: str) -> str:
        """Konvertiert Datumsstring zu ISO-8601."""
        # Bereits ISO-8601
        if 'T' in date_str and 'Z' in date_str:
            return date_str
        
        # Versuche verschiedene Formate
        formats = [
            '%Y-%m-%d',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%d.%m.%Y',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.isoformat() + 'Z'
            except ValueError:
                continue
        
        # Fallback: unverändert zurückgeben
        return date_str
    
    # Hauptnormalisierung
    return clean_dict(payload)


class TritonCore:
    """
    SPEC-002-konformer Triton Core.
    Wrapper für Kompatibilität mit bestehendem Code.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Triton Core.
        
        Args:
            config: Configuration parameters
        """
        self.config = config
        self.seed = config.get('seed', 'MEF_SEED_42')
        self.vector_dim = 5
        self.norm_range = (-1, 1)
    
    def normalize(self, data: Any, data_type: str = 'raw') -> Dict[str, Any]:
        """
        Normalize input data.
        
        Args:
            data: Input data
            data_type: Type hint for data
            
        Returns:
            Normalized data dictionary
        """
        # Konvertiere zu dict falls nötig
        if isinstance(data, dict):
            payload = data
        else:
            payload = {"data": data, "type": data_type}
        
        # SPEC-002 Normalisierung
        normalized = normalize_payload(payload)
        
        # Generiere deterministischen Vektor aus normalisiertem Payload
        import hashlib
        import numpy as np
        
        # Deterministischer Hash aus Payload + Seed
        payload_str = json.dumps(normalized, sort_keys=True)
        hash_input = f"{payload_str}_{self.seed}"
        hash_bytes = hashlib.sha256(hash_input.encode()).digest()
        
        # Konvertiere zu 5D Vektor
        vector = []
        for i in range(5):
            # Nutze 4 Bytes pro Dimension
            byte_slice = hash_bytes[i*4:(i+1)*4]
            value = int.from_bytes(byte_slice, 'big') / (2**32)
            # Skaliere auf [-1, 1]
            vector.append(value * 2 - 1)
        
        base_time = datetime(2025, 1, 1)
        seconds_offset = int.from_bytes(hash_bytes[20:24], 'big') % 86400
        timestamp = (base_time + timedelta(seconds=seconds_offset)).isoformat() + 'Z'

        return {
            'vector': vector,
            'original_type': type(data).__name__,
            'data_type': data_type,
            'timestamp': timestamp,
            'metadata': {
                'size': len(payload_str),
                'hash': hashlib.sha256(payload_str.encode()).hexdigest()
            },
            'normalized_payload': normalized
        }