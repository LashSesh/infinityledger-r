"""
Audit and Logging System for MEF-Core
Provides comprehensive logging and audit trail functionality.
"""

import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import zipfile
import csv

class MEFAuditLogger:
    """
    Audit logger for MEF-Core system.
    Tracks all operations and provides audit trail export.
    """
    
    def __init__(self, log_path: str = "C:/MEF/logs"):
        """
        Initialize audit logger.
        
        Args:
            log_path: Directory for log storage
        """
        self.log_path = Path(log_path)
        self.log_path.mkdir(parents=True, exist_ok=True)
        
        # Set up file logging
        self.log_file = self.log_path / f"mef_audit_{datetime.now().strftime('%Y%m%d')}.log"
        self.event_log_file = self.log_path / "events.jsonl"
        
        # Configure Python logger
        self.logger = self._setup_logger()
        
        # Event buffer for batch writing
        self.event_buffer = []
        self.buffer_size = 100
    
    def _setup_logger(self) -> logging.Logger:
        """Set up Python logger with appropriate handlers."""
        logger = logging.getLogger("MEF-Core")
        logger.setLevel(logging.DEBUG)
        
        # File handler
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def log_event(self, 
                 event_type: str,
                 component: str,
                 details: Dict[str, Any],
                 severity: str = "INFO") -> str:
        """
        Log a system event.
        
        Args:
            event_type: Type of event (e.g., "SNAPSHOT_CREATED", "TIC_GENERATED")
            component: Component generating the event
            details: Event details
            severity: Log severity level
            
        Returns:
            Event ID
        """
        event_id = self._generate_event_id(event_type, details)
        timestamp = datetime.utcnow().isoformat()
        
        event = {
            "event_id": event_id,
            "timestamp": timestamp,
            "type": event_type,
            "component": component,
            "severity": severity,
            "details": details
        }
        
        # Add to buffer
        self.event_buffer.append(event)
        
        # Write to event log if buffer is full
        if len(self.event_buffer) >= self.buffer_size:
            self._flush_event_buffer()
        
        # Log to Python logger
        log_message = f"[{component}] {event_type}: {event_id}"
        if severity == "ERROR":
            self.logger.error(log_message)
        elif severity == "WARNING":
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)
        
        return event_id
    
    def _generate_event_id(self, event_type: str, details: Dict[str, Any]) -> str:
        """Generate unique event ID."""
        content = f"{event_type}_{datetime.utcnow().isoformat()}_{json.dumps(details)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _flush_event_buffer(self):
        """Write buffered events to disk."""
        if not self.event_buffer:
            return
        
        with open(self.event_log_file, 'a') as f:
            for event in self.event_buffer:
                f.write(json.dumps(event) + "\n")
        
        self.event_buffer.clear()
    
    def log_snapshot_creation(self, snapshot: Dict[str, Any]) -> str:
        """Log snapshot creation event."""
        return self.log_event(
            "SNAPSHOT_CREATED",
            "Spiral",
            {
                "snapshot_id": snapshot['id'],
                "seed": snapshot['seed'],
                "phase": snapshot['phase'],
                "por": snapshot['metrics']['por']
            }
        )
    
    def log_tic_generation(self, tic: Dict[str, Any], convergence_info: Dict[str, Any]) -> str:
        """Log TIC generation event."""
        return self.log_event(
            "TIC_GENERATED",
            "TIC-Crystallizer",
            {
                "tic_id": tic['tic_id'],
                "source_snapshot": tic['source_snapshot'],
                "converged": convergence_info.get('converged', False),
                "iterations": convergence_info.get('iterations', 0),
                "por": tic['proof']['por']
            }
        )
    
    def log_ledger_commit(self, block: Dict[str, Any]) -> str:
        """Log ledger commit event."""
        return self.log_event(
            "LEDGER_COMMIT",
            "MEF-Ledger",
            {
                "block_index": block['index'],
                "block_hash": block['hash'],
                "tic_id": block['tic_id'],
                "timestamp": block['timestamp']
            }
        )
    
    def log_validation_result(self, 
                             entity_type: str,
                             entity_id: str,
                             is_valid: bool,
                             details: Dict[str, Any]) -> str:
        """Log validation result."""
        return self.log_event(
            f"{entity_type.upper()}_VALIDATION",
            "Validator",
            {
                "entity_id": entity_id,
                "valid": is_valid,
                "details": details
            },
            severity="WARNING" if not is_valid else "INFO"
        )
    
    def log_error(self, component: str, error: Exception, context: Dict[str, Any]) -> str:
        """Log error event."""
        return self.log_event(
            "ERROR",
            component,
            {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context
            },
            severity="ERROR"
        )
    
    def get_events(self, 
                  event_type: Optional[str] = None,
                  component: Optional[str] = None,
                  start_time: Optional[datetime] = None,
                  end_time: Optional[datetime] = None,
                  limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Retrieve events based on filters.
        
        Args:
            event_type: Filter by event type
            component: Filter by component
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of events to return
            
        Returns:
            List of matching events
        """
        # Flush buffer first
        self._flush_event_buffer()
        
        events = []
        
        if self.event_log_file.exists():
            with open(self.event_log_file, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        
                        # Apply filters
                        if event_type and event['type'] != event_type:
                            continue
                        if component and event['component'] != component:
                            continue
                        
                        if start_time or end_time:
                            event_time = datetime.fromisoformat(event['timestamp'])
                            if start_time and event_time < start_time:
                                continue
                            if end_time and event_time > end_time:
                                continue
                        
                        events.append(event)
                        
                        if len(events) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
        
        return events
    
    def generate_audit_report(self, 
                            start_time: Optional[datetime] = None,
                            end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate comprehensive audit report.
        
        Args:
            start_time: Report start time
            end_time: Report end time
            
        Returns:
            Audit report dictionary
        """
        # Get all events in time range
        events = self.get_events(start_time=start_time, end_time=end_time, limit=10000)
        
        # Analyze events
        event_counts = {}
        component_counts = {}
        severity_counts = {"INFO": 0, "WARNING": 0, "ERROR": 0}
        
        for event in events:
            # Count by type
            event_type = event['type']
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            
            # Count by component
            component = event['component']
            component_counts[component] = component_counts.get(component, 0) + 1
            
            # Count by severity
            severity = event.get('severity', 'INFO')
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        # Generate report
        report = {
            "generated": datetime.utcnow().isoformat(),
            "period": {
                "start": start_time.isoformat() if start_time else "beginning",
                "end": end_time.isoformat() if end_time else "current"
            },
            "summary": {
                "total_events": len(events),
                "event_types": len(event_counts),
                "active_components": len(component_counts),
                "errors": severity_counts["ERROR"],
                "warnings": severity_counts["WARNING"]
            },
            "event_counts": event_counts,
            "component_counts": component_counts,
            "severity_counts": severity_counts,
            "recent_errors": [
                e for e in events[-10:] 
                if e.get('severity') == 'ERROR'
            ]
        }
        
        return report
    
    def export_audit_trail(self, 
                          output_path: Optional[str] = None,
                          format: str = "zip",
                          include_logs: bool = True,
                          include_events: bool = True,
                          include_report: bool = True) -> str:
        """
        Export complete audit trail.
        
        Args:
            output_path: Output file path
            format: Export format ("zip", "json", "csv")
            include_logs: Include log files
            include_events: Include event logs
            include_report: Include audit report
            
        Returns:
            Path to exported file
        """
        # Flush buffer
        self._flush_event_buffer()
        
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.log_path / f"audit_export_{timestamp}.{format}"
        else:
            output_path = Path(output_path)
        
        if format == "zip":
            return self._export_as_zip(output_path, include_logs, include_events, include_report)
        elif format == "json":
            return self._export_as_json(output_path, include_events, include_report)
        elif format == "csv":
            return self._export_as_csv(output_path, include_events)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def _export_as_zip(self, 
                      output_path: Path,
                      include_logs: bool,
                      include_events: bool,
                      include_report: bool) -> str:
        """Export as ZIP archive."""
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add log files
            if include_logs:
                for log_file in self.log_path.glob("*.log"):
                    zf.write(log_file, log_file.name)
            
            # Add event log
            if include_events and self.event_log_file.exists():
                zf.write(self.event_log_file, self.event_log_file.name)
            
            # Add audit report
            if include_report:
                report = self.generate_audit_report()
                report_str = json.dumps(report, indent=2)
                zf.writestr("audit_report.json", report_str)
        
        return str(output_path)
    
    def _export_as_json(self, 
                       output_path: Path,
                       include_events: bool,
                       include_report: bool) -> str:
        """Export as JSON file."""
        export_data = {
            "exported": datetime.utcnow().isoformat(),
            "format": "json"
        }
        
        if include_events:
            export_data["events"] = self.get_events(limit=10000)
        
        if include_report:
            export_data["report"] = self.generate_audit_report()
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return str(output_path)
    
    def _export_as_csv(self, output_path: Path, include_events: bool) -> str:
        """Export as CSV file."""
        if not include_events:
            raise ValueError("CSV export requires events to be included")
        
        events = self.get_events(limit=10000)
        
        if not events:
            # Create empty CSV
            with open(output_path, 'w') as f:
                f.write("event_id,timestamp,type,component,severity\n")
            return str(output_path)
        
        # Determine all fields
        all_fields = set()
        for event in events:
            all_fields.update(event.keys())
            if 'details' in event:
                all_fields.update(f"details.{k}" for k in event['details'].keys())
        
        # Remove details field as it's expanded
        all_fields.discard('details')
        fields = sorted(all_fields)
        
        # Write CSV
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            
            for event in events:
                row = {k: v for k, v in event.items() if k != 'details'}
                
                # Flatten details
                if 'details' in event:
                    for k, v in event['details'].items():
                        row[f"details.{k}"] = v
                
                writer.writerow(row)
        
        return str(output_path)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get audit system statistics."""
        # Flush buffer
        self._flush_event_buffer()
        
        # Count log files
        log_files = list(self.log_path.glob("*.log"))
        
        # Calculate sizes
        total_size = sum(f.stat().st_size for f in log_files)
        if self.event_log_file.exists():
            total_size += self.event_log_file.stat().st_size
        
        # Get event count
        event_count = 0
        if self.event_log_file.exists():
            with open(self.event_log_file, 'r') as f:
                event_count = sum(1 for _ in f)
        
        return {
            "log_files": len(log_files),
            "event_count": event_count,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "current_log": str(self.log_file),
            "buffer_size": len(self.event_buffer)
        }
    
    def rotate_logs(self, max_age_days: int = 30, max_size_mb: float = 100):
        """
        Rotate old log files.
        
        Args:
            max_age_days: Maximum age of log files in days
            max_size_mb: Maximum total size of logs in MB
        """
        current_time = datetime.now()
        total_size = 0
        files_by_age = []
        
        # Collect all log files with metadata
        for log_file in self.log_path.glob("*.log"):
            stat = log_file.stat()
            age_days = (current_time - datetime.fromtimestamp(stat.st_mtime)).days
            
            files_by_age.append({
                "path": log_file,
                "age_days": age_days,
                "size": stat.st_size
            })
            total_size += stat.st_size
        
        # Sort by age (oldest first)
        files_by_age.sort(key=lambda x: x["age_days"], reverse=True)
        
        # Remove old files
        for file_info in files_by_age:
            if file_info["age_days"] > max_age_days:
                file_info["path"].unlink()
                total_size -= file_info["size"]
                self.logger.info(f"Rotated old log: {file_info['path'].name}")
            elif total_size > max_size_mb * 1024 * 1024:
                file_info["path"].unlink()
                total_size -= file_info["size"]
                self.logger.info(f"Rotated log for size limit: {file_info['path'].name}")