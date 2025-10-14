"""
S3-Compatible Cloud Storage Adapter for MEF-Core
Provides cloud storage capabilities for snapshots, TICs, and ledger blocks.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import hashlib
import io

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

class S3StorageAdapter:
    """
    S3-compatible storage adapter for MEF-Core artifacts.
    Supports AWS S3, MinIO, and other S3-compatible services.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize S3 adapter.
        
        Args:
            config: S3 configuration including endpoint, credentials, bucket
        """
        self.config = config
        self.bucket_name = config.get('bucket', 'mef-core')
        self.prefix = config.get('prefix', 'mef/')
        
        # Initialize S3 client
        self.s3_client = self._init_s3_client()
        
        # Ensure bucket exists
        self._ensure_bucket()
        
        # Cache for metadata
        self.metadata_cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    def _init_s3_client(self):
        """Initialize S3 client with configuration."""
        s3_config = Config(
            region_name=self.config.get('region', 'us-east-1'),
            signature_version='s3v4',
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )
        
        # Support for custom endpoints (MinIO, etc.)
        endpoint_url = self.config.get('endpoint_url')
        
        # Create client
        return boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=self.config.get('access_key_id', os.environ.get('AWS_ACCESS_KEY_ID')),
            aws_secret_access_key=self.config.get('secret_access_key', os.environ.get('AWS_SECRET_ACCESS_KEY')),
            config=s3_config
        )
    
    def _ensure_bucket(self):
        """Ensure the S3 bucket exists."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Create bucket
                try:
                    if self.config.get('region', 'us-east-1') == 'us-east-1':
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.config['region']}
                        )
                    print(f"Created S3 bucket: {self.bucket_name}")
                    
                    # Set bucket versioning
                    self.s3_client.put_bucket_versioning(
                        Bucket=self.bucket_name,
                        VersioningConfiguration={'Status': 'Enabled'}
                    )
                except ClientError as create_error:
                    raise Exception(f"Failed to create bucket: {create_error}")
            else:
                raise
    
    def _get_s3_key(self, artifact_type: str, artifact_id: str) -> str:
        """
        Generate S3 key for artifact.
        
        Args:
            artifact_type: Type of artifact (snapshot, tic, block, etc.)
            artifact_id: Unique identifier
            
        Returns:
            S3 key path
        """
        type_prefixes = {
            'snapshot': 'snapshots',
            'tic': 'tics',
            'block': 'ledger',
            'hdag': 'hdag',
            'index': 'indices'
        }
        
        type_prefix = type_prefixes.get(artifact_type, 'misc')
        return f"{self.prefix}{type_prefix}/{artifact_id}"
    
    def upload_snapshot(self, snapshot: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Upload snapshot to S3.
        
        Args:
            snapshot: Snapshot data
            
        Returns:
            Tuple of (success, metadata)
        """
        snapshot_id = snapshot['id']
        key = self._get_s3_key('snapshot', f"{snapshot_id}.spiral")
        
        try:
            # Serialize snapshot
            snapshot_json = json.dumps(snapshot, sort_keys=True, indent=2)
            
            # Calculate checksum
            checksum = hashlib.sha256(snapshot_json.encode()).hexdigest()
            
            # Upload to S3
            response = self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=snapshot_json,
                ContentType='application/json',
                Metadata={
                    'snapshot-id': snapshot_id,
                    'seed': snapshot['seed'],
                    'phase': str(snapshot['phase']),
                    'por': snapshot['metrics']['por'],
                    'checksum': checksum,
                    'timestamp': snapshot['timestamp']
                }
            )
            
            # Update cache
            self.metadata_cache[snapshot_id] = {
                'key': key,
                'etag': response['ETag'],
                'checksum': checksum,
                'uploaded': datetime.utcnow().isoformat()
            }
            
            return True, {
                'key': key,
                'etag': response['ETag'],
                'version_id': response.get('VersionId'),
                'checksum': checksum
            }
            
        except ClientError as e:
            return False, {'error': str(e)}
    
    def download_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Download snapshot from S3.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            Snapshot data or None
        """
        key = self._get_s3_key('snapshot', f"{snapshot_id}.spiral")
        
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            # Read and parse JSON
            snapshot_json = response['Body'].read().decode('utf-8')
            snapshot = json.loads(snapshot_json)
            
            # Verify checksum if available
            if 'checksum' in response['Metadata']:
                expected_checksum = response['Metadata']['checksum']
                actual_checksum = hashlib.sha256(snapshot_json.encode()).hexdigest()
                
                if expected_checksum != actual_checksum:
                    print(f"Warning: Checksum mismatch for snapshot {snapshot_id}")
            
            return snapshot
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            raise
    
    def upload_tic(self, tic: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Upload TIC to S3.
        
        Args:
            tic: TIC data
            
        Returns:
            Tuple of (success, metadata)
        """
        tic_id = tic['tic_id']
        key = self._get_s3_key('tic', f"{tic_id}.tic")
        
        try:
            # Serialize TIC
            tic_json = json.dumps(tic, sort_keys=True, indent=2)
            
            # Upload to S3
            response = self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=tic_json,
                ContentType='application/json',
                Metadata={
                    'tic-id': tic_id,
                    'seed': tic['seed'],
                    'source-snapshot': tic['source_snapshot'],
                    'por': tic['proof']['por']
                }
            )
            
            return True, {
                'key': key,
                'etag': response['ETag'],
                'version_id': response.get('VersionId')
            }
            
        except ClientError as e:
            return False, {'error': str(e)}
    
    def download_tic(self, tic_id: str) -> Optional[Dict[str, Any]]:
        """
        Download TIC from S3.
        
        Args:
            tic_id: TIC identifier
            
        Returns:
            TIC data or None
        """
        key = self._get_s3_key('tic', f"{tic_id}.tic")
        
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            tic_json = response['Body'].read().decode('utf-8')
            return json.loads(tic_json)
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            raise
    
    def upload_block(self, block: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Upload ledger block to S3.
        
        Args:
            block: Block data
            
        Returns:
            Tuple of (success, metadata)
        """
        block_index = block['index']
        key = self._get_s3_key('block', f"block_{block_index:06d}.mef")
        
        try:
            # Serialize block
            block_json = json.dumps(block, sort_keys=True, indent=2)
            
            # Upload to S3 with server-side encryption
            response = self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=block_json,
                ContentType='application/json',
                ServerSideEncryption='AES256',
                Metadata={
                    'block-index': str(block_index),
                    'block-hash': block['hash'],
                    'tic-id': block['tic_id'],
                    'timestamp': block['timestamp']
                }
            )
            
            return True, {
                'key': key,
                'etag': response['ETag'],
                'version_id': response.get('VersionId')
            }
            
        except ClientError as e:
            return False, {'error': str(e)}
    
    def download_block(self, block_index: int) -> Optional[Dict[str, Any]]:
        """
        Download ledger block from S3.
        
        Args:
            block_index: Block index
            
        Returns:
            Block data or None
        """
        key = self._get_s3_key('block', f"block_{block_index:06d}.mef")
        
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            block_json = response['Body'].read().decode('utf-8')
            return json.loads(block_json)
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            raise
    
    def list_artifacts(self, 
                      artifact_type: str,
                      prefix_filter: Optional[str] = None,
                      max_items: int = 1000) -> List[Dict[str, Any]]:
        """
        List artifacts in S3.
        
        Args:
            artifact_type: Type of artifacts to list
            prefix_filter: Additional prefix filter
            max_items: Maximum number of items to return
            
        Returns:
            List of artifact metadata
        """
        base_prefix = self._get_s3_key(artifact_type, '')
        if prefix_filter:
            base_prefix = f"{base_prefix}{prefix_filter}"
        
        artifacts = []
        
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=base_prefix,
                PaginationConfig={'MaxItems': max_items}
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        # Get object metadata
                        head_response = self.s3_client.head_object(
                            Bucket=self.bucket_name,
                            Key=obj['Key']
                        )
                        
                        artifacts.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat(),
                            'etag': obj['ETag'],
                            'metadata': head_response.get('Metadata', {})
                        })
            
        except ClientError as e:
            print(f"Error listing artifacts: {e}")
        
        return artifacts
    
    def sync_to_s3(self, local_path: Path, artifact_type: str) -> Dict[str, Any]:
        """
        Sync local directory to S3.
        
        Args:
            local_path: Local directory path
            artifact_type: Type of artifacts being synced
            
        Returns:
            Sync statistics
        """
        stats = {
            'uploaded': 0,
            'skipped': 0,
            'failed': 0,
            'errors': []
        }
        
        # Map file extensions to artifact types
        ext_map = {
            '.spiral': 'snapshot',
            '.tic': 'tic',
            '.mef': 'block'
        }
        
        for file_path in local_path.rglob('*'):
            if file_path.is_file():
                ext = file_path.suffix
                if ext in ext_map:
                    # Read file
                    with open(file_path, 'r') as f:
                        try:
                            data = json.load(f)
                            
                            # Upload based on type
                            if ext == '.spiral':
                                success, _ = self.upload_snapshot(data)
                            elif ext == '.tic':
                                success, _ = self.upload_tic(data)
                            elif ext == '.mef':
                                success, _ = self.upload_block(data)
                            else:
                                success = False
                            
                            if success:
                                stats['uploaded'] += 1
                            else:
                                stats['failed'] += 1
                                
                        except Exception as e:
                            stats['failed'] += 1
                            stats['errors'].append(f"{file_path.name}: {str(e)}")
                else:
                    stats['skipped'] += 1
        
        return stats
    
    def sync_from_s3(self, local_path: Path, artifact_type: str) -> Dict[str, Any]:
        """
        Sync from S3 to local directory.
        
        Args:
            local_path: Local directory path
            artifact_type: Type of artifacts to sync
            
        Returns:
            Sync statistics
        """
        stats = {
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
            'errors': []
        }
        
        artifacts = self.list_artifacts(artifact_type)
        
        for artifact in artifacts:
            key = artifact['key']
            filename = Path(key).name
            local_file = local_path / filename
            
            # Check if file exists and is up to date
            if local_file.exists():
                # Compare checksums or timestamps
                stats['skipped'] += 1
                continue
            
            try:
                # Download object
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=key
                )
                
                # Save to local file
                with open(local_file, 'wb') as f:
                    f.write(response['Body'].read())
                
                stats['downloaded'] += 1
                
            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append(f"{filename}: {str(e)}")
        
        return stats
    
    def create_presigned_url(self, 
                           artifact_type: str,
                           artifact_id: str,
                           expiration: int = 3600) -> Optional[str]:
        """
        Create presigned URL for direct access.
        
        Args:
            artifact_type: Type of artifact
            artifact_id: Artifact identifier
            expiration: URL expiration time in seconds
            
        Returns:
            Presigned URL or None
        """
        key = self._get_s3_key(artifact_type, artifact_id)
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expiration
            )
            return url
        except ClientError:
            return None
    
    def enable_versioning(self) -> bool:
        """Enable versioning on the S3 bucket."""
        try:
            self.s3_client.put_bucket_versioning(
                Bucket=self.bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )
            return True
        except ClientError:
            return False
    
    def set_lifecycle_policy(self, days_to_glacier: int = 30, days_to_delete: int = 365) -> bool:
        """
        Set lifecycle policy for automatic archival and deletion.
        
        Args:
            days_to_glacier: Days before moving to Glacier storage
            days_to_delete: Days before permanent deletion
            
        Returns:
            Success status
        """
        lifecycle_policy = {
            'Rules': [
                {
                    'ID': 'MEF-Core-Lifecycle',
                    'Status': 'Enabled',
                    'Prefix': self.prefix,
                    'Transitions': [
                        {
                            'Days': days_to_glacier,
                            'StorageClass': 'GLACIER'
                        }
                    ],
                    'Expiration': {
                        'Days': days_to_delete
                    }
                }
            ]
        }
        
        try:
            self.s3_client.put_bucket_lifecycle_configuration(
                Bucket=self.bucket_name,
                LifecycleConfiguration=lifecycle_policy
            )
            return True
        except ClientError:
            return False
    
    def get_storage_metrics(self) -> Dict[str, Any]:
        """Get S3 storage metrics."""
        metrics = {
            'bucket': self.bucket_name,
            'prefix': self.prefix,
            'artifacts': {},
            'total_size': 0,
            'total_objects': 0
        }
        
        artifact_types = ['snapshot', 'tic', 'block']
        
        for artifact_type in artifact_types:
            prefix = self._get_s3_key(artifact_type, '')
            
            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix
                )
                
                if 'Contents' in response:
                    objects = response['Contents']
                    total_size = sum(obj['Size'] for obj in objects)
                    
                    metrics['artifacts'][artifact_type] = {
                        'count': len(objects),
                        'size_bytes': total_size,
                        'size_mb': total_size / (1024 * 1024)
                    }
                    
                    metrics['total_size'] += total_size
                    metrics['total_objects'] += len(objects)
                else:
                    metrics['artifacts'][artifact_type] = {
                        'count': 0,
                        'size_bytes': 0,
                        'size_mb': 0
                    }
                    
            except ClientError:
                metrics['artifacts'][artifact_type] = {'error': 'Unable to retrieve'}
        
        metrics['total_size_mb'] = metrics['total_size'] / (1024 * 1024)
        
        return metrics